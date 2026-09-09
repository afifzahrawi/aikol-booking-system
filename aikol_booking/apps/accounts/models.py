"""The custom user model.

This lands in the first migration deliberately. Swapping Django's user model
after tables exist means recreating the database, so the shape has to be right
before anything references it.

Email is the login field, not a username and not the matriculation number. The
matriculation or staff number is collected for documentation and reporting
(decision 18) and is unique, but it is not a credential — people mistype them,
they change form between intakes, and a login field has to be stable.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    """What a person may do. Distinct from affiliation — see below."""

    USER = "USER", "User"
    APPROVER = "APPROVER", "Approver"          # decides bookings only (decision 5)
    ADMINISTRATOR = "ADMINISTRATOR", "Administrator"


class Affiliation(models.TextChoices):
    """What a person *is*. Distinct from role.

    Role grants authority inside the system; affiliation describes the person's
    relationship to the University. They are separate fields because they vary
    independently: a lecturer may be an ordinary user, and an administrator may
    be a member of staff who never drives.
    """

    STUDENT = "STUDENT", "Student"
    LECTURER = "LECTURER", "Lecturer"
    STAFF = "STAFF", "Staff"
    PUBLIC = "PUBLIC", "Member of the public"


phone_validator = RegexValidator(
    r"^[0-9+\-\s()]{7,20}$",
    "Enter a telephone number using digits, spaces, and + - ( ) only.",
)


class UserManager(BaseUserManager):
    """Manager for a user model whose natural key is an email address."""

    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("role", Role.USER)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("role", Role.ADMINISTRATOR)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        extra.setdefault("email_verified", True)
        if extra.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """A person who can sign in.

    Deactivated, never deleted, while any booking references them
    (`bookings.user` is PROTECT). `is_active = False` is how an account is
    retired; the row and its history stay.
    """

    email = models.EmailField(
        "email address",
        unique=True,
        help_text="The login field. IIUM addresses identify staff and students.",
    )
    full_name = models.CharField(max_length=150)

    # Unique, but nullable: a member of the public has neither number, and a
    # column of empty strings would collide under a unique constraint.
    identification_number = models.CharField(
        "matriculation or staff number",
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        help_text="Collected for documentation and reporting (decision 18). Not a login credential.",
    )
    phone = models.CharField(max_length=20, validators=[phone_validator])

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    affiliation = models.CharField(
        max_length=20, choices=Affiliation.choices, default=Affiliation.STUDENT
    )

    # Registration is open, but an unverified account cannot book anything.
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    # Captured on the first self-drive vehicle booking, not at registration —
    # most people never need them. Personal data: excluded from the audit log's
    # free text and from exports that do not require them.
    licence_number = models.CharField("driving licence number", max_length=30, blank=True)
    licence_expiry = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # access to Django's own admin
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ("full_name",)
        indexes = [models.Index(fields=["role"]), models.Index(fields=["affiliation"])]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"

    # -- Authority -------------------------------------------------------
    # Checked in views, never inferred from a hidden menu item.

    @property
    def initials(self) -> str:
        """Two letters for the avatar. Titles are dropped — "Dr Hafiz Rahman"
        is HR, not DH."""
        words = [w for w in self.full_name.split() if w.lower().rstrip(".") not in
                 ("dr", "prof", "professor", "mr", "mrs", "ms", "assoc")]
        return "".join(w[0] for w in words[:2]).upper() or "?"

    @property
    def is_administrator(self) -> bool:
        return self.role == Role.ADMINISTRATOR

    @property
    def is_approver(self) -> bool:
        """An administrator can do everything an approver can."""
        return self.role in (Role.APPROVER, Role.ADMINISTRATOR)

    @property
    def can_book(self) -> bool:
        """No booking of any kind until the address is confirmed."""
        return self.is_active and self.email_verified

    @property
    def may_drive(self) -> bool:
        """Eligibility to DRIVE, which is not eligibility to book.

        Anyone may request a car. A student may never drive a Kulliyyah car, so
        a student's booking must request a VMU driver instead. Keeping these two
        questions apart is the whole point of the property.
        """
        return self.affiliation in (Affiliation.LECTURER, Affiliation.STAFF)

    @property
    def has_iium_email(self) -> bool:
        from django.conf import settings

        domain = self.email.rsplit("@", 1)[-1].lower()
        return domain in settings.IIUM_EMAIL_DOMAINS

    def mark_email_verified(self) -> None:
        self.email_verified = True
        self.email_verified_at = timezone.now()
        self.save(update_fields=["email_verified", "email_verified_at"])

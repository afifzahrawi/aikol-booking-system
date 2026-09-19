(function () {
    "use strict";

    function initialise(container) {
    container.querySelectorAll("[data-user-combobox]").forEach(function (root) {
        if (root.dataset.comboboxReady === "true") return;
        root.dataset.comboboxReady = "true";
        var search = root.querySelector('[role="combobox"]');
        var hidden = root.querySelector('input[name="on_behalf_of"]');
        var results = root.querySelector('[role="listbox"]');
        var clear = root.querySelector(".combobox-clear");
        var timer;
        var active = -1;

        function close() {
            results.hidden = true;
            results.innerHTML = "";
            search.setAttribute("aria-expanded", "false");
            search.removeAttribute("aria-activedescendant");
            active = -1;
        }

        function choose(button) {
            hidden.value = button.dataset.id;
            search.value = button.dataset.label;
            clear.hidden = false;
            close();
            search.focus();
        }

        function move(delta) {
            var options = Array.prototype.slice.call(results.querySelectorAll('[role="option"]'));
            if (!options.length) return;
            active = (active + delta + options.length) % options.length;
            options.forEach(function (option, index) {
                option.setAttribute("aria-selected", index === active ? "true" : "false");
            });
            search.setAttribute("aria-activedescendant", options[active].id);
            options[active].scrollIntoView({ block: "nearest" });
        }

        function render(items) {
            results.innerHTML = "";
            if (!items.length) {
                var empty = document.createElement("p");
                empty.className = "combobox-empty";
                empty.textContent = "No verified active account matches that search.";
                results.appendChild(empty);
            } else {
                items.forEach(function (person, index) {
                    var button = document.createElement("button");
                    button.type = "button";
                    button.id = "booking-user-option-" + index;
                    button.setAttribute("role", "option");
                    button.setAttribute("aria-selected", "false");
                    button.dataset.id = person.id;
                    button.dataset.label = person.label + " — " + person.meta;
                    var name = document.createElement("strong");
                    name.textContent = person.label;
                    var meta = document.createElement("span");
                    meta.textContent = person.meta;
                    button.appendChild(name);
                    button.appendChild(meta);
                    button.addEventListener("click", function () { choose(button); });
                    results.appendChild(button);
                });
            }
            results.hidden = false;
            search.setAttribute("aria-expanded", "true");
        }

        search.addEventListener("input", function () {
            hidden.value = "";
            clear.hidden = true;
            window.clearTimeout(timer);
            var query = search.value.trim();
            if (query.length < 2) {
                close();
                return;
            }
            timer = window.setTimeout(function () {
                fetch(root.dataset.source + "?q=" + encodeURIComponent(query), {
                    headers: { "X-Requested-With": "XMLHttpRequest" }
                })
                    .then(function (response) {
                        if (!response.ok) throw new Error("Search unavailable");
                        return response.json();
                    })
                    .then(function (data) { render(data.results || []); })
                    .catch(function () {
                        render([]);
                        results.querySelector(".combobox-empty").textContent =
                            "Account search is unavailable. Try again.";
                    });
            }, 180);
        });

        search.addEventListener("keydown", function (event) {
            if (event.key === "ArrowDown") { event.preventDefault(); move(1); }
            else if (event.key === "ArrowUp") { event.preventDefault(); move(-1); }
            else if (event.key === "Enter" && active >= 0) {
                event.preventDefault();
                choose(results.querySelectorAll('[role="option"]')[active]);
            } else if (event.key === "Escape") close();
        });

        clear.addEventListener("click", function () {
            hidden.value = "";
            search.value = "";
            clear.hidden = true;
            close();
            search.focus();
        });
        clear.hidden = !hidden.value;
        document.addEventListener("click", function (event) {
            if (!root.contains(event.target)) close();
        });
    });
    }

    initialise(document);
    document.addEventListener("aikol:modal-content", function (event) {
        initialise(event.detail.root);
    });
}());

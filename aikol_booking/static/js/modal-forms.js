(function () {
    'use strict';

    const dialog = document.getElementById('actionDialog');
    const body = dialog && dialog.querySelector('[data-dialog-body]');
    const title = dialog && dialog.querySelector('#actionDialogTitle');
    const close = dialog && dialog.querySelector('[data-dialog-close]');
    if (!dialog || !body || !title || !close) return;

    let sourceUrl = window.location.href;

    // A popup that says only "it did not work" leaves somebody stuck: they
    // cannot tell whether the decision was recorded, and the popup offers no
    // way out. Say what happened, and always offer the full page.
    function failureNotice(message, url) {
        const link = url ? ` <a href="${url}">Open the full page</a>.` : "";
        return `<p class="notice notice-error" role="alert">${message}${link}</p>`;
    }

    function describeStatus(status) {
        if (status === 403) {
            return "Your session has expired, so that was not saved. Reload the page and sign in again.";
        }
        if (status === 404) {
            return "That record is no longer there. It may already have been decided.";
        }
        if (status >= 500) {
            return "The server could not complete that. It may not have been saved.";
        }
        return "That could not be completed.";
    }

    function setBusy(label) {
        title.textContent = label || 'Action';
        body.innerHTML = '<p class="action-dialog-loading" role="status">Loading form…</p>';
    }

    function modalContent(documentFragment) {
        const main = documentFragment.querySelector('main');
        if (!main) return null;
        const clone = main.cloneNode(true);
        clone.querySelectorAll('.back-navigation, .page-head .btn-group').forEach(node => node.remove());
        return clone;
    }

    function wireForm(form, actionUrl) {
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const submitter = event.submitter;
            const data = new FormData(form);
            if (submitter && submitter.name && !data.has(submitter.name)) {
                data.append(submitter.name, submitter.value);
            }
            form.setAttribute('aria-busy', 'true');
            if (submitter) submitter.disabled = true;
            try {
                // A form without an action inherits the outer page URL when its
                // markup is moved into this dialog. Post it to the fetched form
                // endpoint instead of the list page behind the dialog.
                const response = await fetch(form.getAttribute('action') || actionUrl, {
                    method: (form.method || 'post').toUpperCase(),
                    body: data,
                    credentials: 'same-origin',
                    headers: {'X-Requested-With': 'XMLHttpRequest'}
                });
                if (response.status === 204) {
                    dialog.close();
                    window.location.reload();
                    return;
                }
                if (response.redirected) {
                    dialog.close();
                    // Follow the server's own redirect. Returning to the page
                    // that launched the dialog left a deleted record on screen
                    // and, when that page was the record itself, would have
                    // reloaded a 404. A same-URL assign can also come from the
                    // cache, so that case reloads.
                    const target = new URL(response.url, window.location.href);
                    if (target.href === window.location.href) {
                        window.location.reload();
                    } else {
                        window.location.assign(target.href);
                    }
                    return;
                }
                if (!response.ok) {
                    body.insertAdjacentHTML(
                        'afterbegin',
                        failureNotice(describeStatus(response.status), actionUrl)
                    );
                    return;
                }
                const html = await response.text();
                const parsed = new DOMParser().parseFromString(html, 'text/html');
                render(parsed, actionUrl);
            } catch (error) {
                console.error('Modal form submit failed', error);
                body.insertAdjacentHTML(
                    'afterbegin',
                    failureNotice(
                        'The connection broke before the reply arrived. It may still have been saved: reload the page and check before trying again.',
                        actionUrl
                    )
                );
            } finally {
                form.removeAttribute('aria-busy');
                if (submitter) submitter.disabled = false;
            }
        });
    }

    function render(parsed, actionUrl) {
        const content = modalContent(parsed);
        if (!content) {
            window.location.assign(actionUrl);
            return;
        }
        const heading = content.querySelector('h1');
        title.textContent = heading ? heading.textContent.trim() : 'Action';
        if (heading) heading.remove();
        content.querySelectorAll('a.btn').forEach(link => {
            if (/^(Back|Cancel|Keep)/i.test(link.textContent.trim())) {
                link.href = '#';
                link.addEventListener('click', event => {
                    event.preventDefault();
                    dialog.close();
                });
            }
        });
        body.replaceChildren(...content.childNodes);
        document.dispatchEvent(new CustomEvent('aikol:modal-content', {detail: {root: body}}));
        const form = body.querySelector('form');
        if (form) wireForm(form, actionUrl);
        window.setTimeout(() => {
            const focusTarget = body.querySelector('.form-error-summary, input:not([type="hidden"]), select, textarea, button');
            if (focusTarget) focusTarget.focus();
        }, 0);
    }

    async function openAction(link) {
        sourceUrl = window.location.href;
        dialog.classList.toggle('action-dialog-wide', link.dataset.modalSize === 'wide');
        setBusy(link.textContent.trim());
        dialog.showModal();
        try {
            const response = await fetch(link.href, {
                credentials: 'same-origin',
                headers: {'X-Requested-With': 'XMLHttpRequest'}
            });
            if (!response.ok) {
                body.innerHTML = failureNotice(describeStatus(response.status), link.href);
                return;
            }
            const html = await response.text();
            render(new DOMParser().parseFromString(html, 'text/html'), link.href);
        } catch (error) {
            console.error('Modal form open failed', error);
            body.innerHTML = failureNotice(
                'That did not load. Check your connection and try again.',
                link.href
            );
        }
    }

    document.addEventListener('click', event => {
        const link = event.target.closest('a[data-modal-form]');
        if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        openAction(link);
    });
    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {
        if (event.target === dialog) dialog.close();
    });
})();

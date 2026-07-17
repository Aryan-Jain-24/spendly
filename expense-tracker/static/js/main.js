// main.js — students will add JavaScript here as features are built

document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".transaction-delete-form").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (!confirm("Delete this expense?")) {
                event.preventDefault();
            }
        });
    });
});

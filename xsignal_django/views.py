from django.shortcuts import render


def _render_generic_error(request, status_code: int, title: str, description: str):
    context = {
        "status_code": status_code,
        "title": title,
        "description": description,
    }
    return render(request, "errors/generic_error.html", context=context, status=status_code)


def handler403(request, exception):
    return _render_generic_error(
        request,
        403,
        "Access denied",
        "You do not have permission to view this page.",
    )


def handler404(request, exception):
    return _render_generic_error(
        request,
        404,
        "Page not found",
        "The page you are looking for does not exist.",
    )

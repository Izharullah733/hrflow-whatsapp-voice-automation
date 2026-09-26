def dashboard_context(request):
    user = request.user
    return {"can_edit": user.is_authenticated and (user.is_superuser or user.groups.filter(name="HR").exists()),
            "is_admin": user.is_authenticated and user.is_superuser}

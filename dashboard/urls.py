from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from .views import (
    admin_delete_dashboard,
    admin_delete_user,
    admin_console,
    ai_overview,
    create_user_dashboard,
    dashboard,
    dashboard_hub,
    delete_user_dashboard,
    edit_user_dashboard,
    home,
    latest_n8n_reply,
    n8n_reply,
    sync_dashboard_posts,
    signup,
)


urlpatterns = [
    path("home/", home, name="home"),
    path("auth/signup/", signup, name="signup"),
    path("auth/login/", LoginView.as_view(template_name="dashboard/auth/login.html"), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("workspaces/", dashboard_hub, name="dashboard_hub"),
    path("workspaces/create/", create_user_dashboard, name="create_user_dashboard"),
    path("workspaces/<int:workspace_id>/edit/", edit_user_dashboard, name="edit_user_dashboard"),
    path("workspaces/<int:workspace_id>/delete/", delete_user_dashboard, name="delete_user_dashboard"),
    path("workspaces/<int:workspace_id>/sync/", sync_dashboard_posts, name="sync_dashboard_posts"),
    path("", dashboard, name="dashboard"),
    path("admin-console/", admin_console, name="admin_console"),
    path("admin-console/users/<int:user_id>/delete/", admin_delete_user, name="admin_delete_user"),
    path("admin-console/workspaces/<int:workspace_id>/delete/", admin_delete_dashboard, name="admin_delete_dashboard"),
    path("ai-overview/", ai_overview, name="ai_overview"),
    path("n8n/reply/", n8n_reply, name="n8n_reply"),
    path("n8n/reply/latest/", latest_n8n_reply, name="latest_n8n_reply"),
]

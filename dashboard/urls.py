from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from .views import (
    ai_overview,
    create_user_dashboard,
    dashboard,
    dashboard_hub,
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
    path("workspaces/<int:workspace_id>/sync/", sync_dashboard_posts, name="sync_dashboard_posts"),
    path("", dashboard, name="dashboard"),
    path("ai-overview/", ai_overview, name="ai_overview"),
    path("n8n/reply/", n8n_reply, name="n8n_reply"),
    path("n8n/reply/latest/", latest_n8n_reply, name="latest_n8n_reply"),
]

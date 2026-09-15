from django.urls import path

from apps.dashboard import api, views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('coin/<str:base_asset>/', views.coin_page, name='coin_page'),
    # API
    path('api/overview/', api.overview, name='api-overview'),
    path('api/coin/<str:base_asset>/', api.coin_detail, name='api-coin'),
    path('api/coin/<str:base_asset>/candles/<str:timeframe>/',
         api.candles, name='api-candles'),
    path('api/performance/', api.performance, name='api-performance'),
    path('api/notifications/', api.notifications, name='api-notifications'),
    path('api/reconnect/', api.reconnect, name='api-reconnect'),
]

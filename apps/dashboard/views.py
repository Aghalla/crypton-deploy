from django.conf import settings
from django.shortcuts import get_object_or_404, render

from apps.market_data.models import Coin
from apps.market_data.services.data import is_connected


def dashboard(request):
    coins = Coin.objects.filter(is_active=True).select_related('ticker')
    return render(request, 'dashboard/dashboard.html', {
        'coins': coins,
        'connected': is_connected(),
    })


def coin_page(request, base_asset):
    coin = get_object_or_404(Coin, base_asset__iexact=base_asset, is_active=True)
    return render(request, 'dashboard/coin.html', {'coin': coin})

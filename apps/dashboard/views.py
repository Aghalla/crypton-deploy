from django.conf import settings
from django.shortcuts import get_object_or_404, render

from apps.market_data.models import Coin


def dashboard(request):
    coins = Coin.objects.filter(is_active=True).select_related('ticker')
    demo_mode = getattr(settings, 'DEMO_MODE', False)
    return render(request, 'dashboard/dashboard.html', {
        'coins': coins,
        'demo_mode': demo_mode,
    })


def coin_page(request, base_asset):
    coin = get_object_or_404(Coin, base_asset__iexact=base_asset, is_active=True)
    return render(request, 'dashboard/coin.html', {'coin': coin})

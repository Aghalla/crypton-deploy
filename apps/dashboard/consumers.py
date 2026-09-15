"""
WebSocket consumer: pushes price updates and new-signal events to the browser
so the dashboard never needs a refresh.
"""
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger('crypton.ws')

GROUP = 'dashboard'


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add(GROUP, self.channel_name)
        await self.accept()
        await self.send_json({'type': 'overview',
                              'payload': await get_overview()})

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get('type') == 'refresh':
            await self.send_json({'type': 'overview',
                                  'payload': await get_overview()})

    # group broadcast handlers -------------------------------------------
    async def overview_event(self, event):
        await self.send_json({'type': 'overview', 'payload': event['payload']})

    async def signal_event(self, event):
        await self.send_json({'type': 'signal', 'payload': event['payload']})


@database_sync_to_async
def get_overview():
    from apps.dashboard.api import build_overview
    return build_overview()

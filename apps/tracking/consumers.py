import json
import math
from django.utils import timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ActiveTracker, LocationHistory, TrackingStatus

class LocationTrackingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = str(self.scope["url_route"]["kwargs"]["room_id"])
        self.tracking_group_name = f"tracking_{self.room_id}"
        self.user = self.scope.get("user")

        # 1. Reject anonymous connections immediately
        if not self.user or self.user.is_anonymous:
            await self.close(code=4003)
            return

        # 2. Check if the active tracker exists for this room
        self.tracker_exists = await self.verify_tracker_and_membership()
        if not self.tracker_exists:
            await self.close(code=4003)
            return

        # 3. Add to the room's tracking channel group
        await self.channel_layer.group_add(self.tracking_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "tracking_group_name"):
            await self.channel_layer.group_discard(self.tracking_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return

        event = payload.get("event")
        data = payload.get("data", {})

        # Ensure only the designated tracker_user can update the location or state
        if not await self.is_authorized_tracker():
            return

        if event == "location_update":
            metrics = await self.process_location_update(data)
            if metrics:
                await self.channel_layer.group_send(
                    self.tracking_group_name,
                    {
                        "type": "broadcast_event",
                        "payload": {
                            "event": "location_update",
                            "data": metrics
                        }
                    }
                )

        elif event == "status_update":
            new_status = data.get("status")
            if new_status in TrackingStatus.values:
                updated_status = await self.update_tracker_status(new_status)
                await self.channel_layer.group_send(
                    self.tracking_group_name,
                    {
                        "type": "broadcast_event",
                        "payload": {
                            "event": "status_update",
                            "data": {
                                "status": updated_status,
                                "updated_at": timezone.now().isoformat()
                            }
                        }
                    }
                )

    async def broadcast_event(self, event):
        """Sends the group broadcast directly over the active socket."""
        await self.send(text_data=json.dumps(event["payload"]))

    # --- Database Operations (Async Bridges) ---

    @database_sync_to_async
    def verify_tracker_and_membership(self):
        try:
            # Optimize with a fast check. The tracking room participants must include self.user
            tracker = ActiveTracker.objects.select_related("room").get(room_id=self.room_id)
            return tracker.room.participants.filter(id=self.user.id).exists()
        except ActiveTracker.DoesNotExist:
            return False

    @database_sync_to_async
    def is_authorized_tracker(self):
        return ActiveTracker.objects.filter(room_id=self.room_id, tracker_user=self.user).exists()

    @database_sync_to_async
    def update_tracker_status(self, new_status):
        tracker = ActiveTracker.objects.get(room_id=self.room_id)
        tracker.status = new_status
        tracker.save(update_fields=["status", "updated_at"])
        return tracker.status

    @database_sync_to_async
    def process_location_update(self, data):
        try:
            tracker = ActiveTracker.objects.get(room_id=self.room_id)
            
            # Extract raw coordinates
            lat = float(data["lat"])
            lng = float(data["lng"])
            
            # Calculate remaining distance using Haversine Formula
            R = 6371.0  # Earth's radius in kilometers
            lat1, lon1 = math.radians(lat), math.radians(lng)
            lat2, lon2 = math.radians(tracker.destination_lat), math.radians(tracker.destination_lng)
            
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            
            a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance = round(R * c, 2)

            # Estimate ETA (Simple dynamic speed calculation fallback to standard 25km/h speed limits)
            current_speed_mps = float(data.get("speed", 0) or 0)
            current_speed_kph = current_speed_mps * 3.6
            speed_reference = current_speed_kph if current_speed_kph > 5 else 25.0
            
            eta_hours = distance / speed_reference
            eta_minutes = max(1, int(eta_hours * 60))

            # Update Tracker instance with incoming telemetry
            tracker.current_lat = lat
            tracker.current_lng = lng
            tracker.speed = current_speed_mps
            tracker.heading = float(data.get("heading", 0) or 0)
            tracker.accuracy = float(data.get("accuracy")) if data.get("accuracy") is not None else None
            tracker.altitude = float(data.get("altitude")) if data.get("altitude") is not None else None
            tracker.distance_remaining_km = distance
            tracker.eta_minutes = eta_minutes
            tracker.save()

            # Append coordinates to structural LocationHistory
            LocationHistory.objects.create(
                tracker=tracker,
                latitude=lat,
                longitude=lng,
                speed=tracker.speed,
                heading=tracker.heading,
                accuracy=tracker.accuracy,
                altitude=tracker.altitude
            )

            return {
                "current_lat": lat,
                "current_lng": lng,
                "speed": tracker.speed,
                "heading": tracker.heading,
                "accuracy": tracker.accuracy,
                "altitude": tracker.altitude,
                "distance_remaining_km": distance,
                "eta_minutes": eta_minutes,
                "status": tracker.status
            }
        except (ActiveTracker.DoesNotExist, KeyError, ValueError):
            return None
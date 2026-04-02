"""
generate_token.py — Generates a LiveKit access token for joining the pitch room.

Run once before opening the browser playground:
  python generate_token.py

Copy the printed token and paste it into https://agents-playground.livekit.io
under the "Custom" tab → Token field.
"""

from livekit.api import AccessToken, VideoGrants

token = (
    AccessToken(api_key="devkey", api_secret="secret")
    .with_identity("founder")
    .with_name("Founder")
    .with_grants(VideoGrants(room_join=True, room="pitch-room"))
    .to_jwt()
)

print("\n===== YOUR TOKEN (copy everything below this line) =====")
print(token)
print("========================================================")
print("\nPlayground URL : https://agents-playground.livekit.io")
print("Server URL     : ws://localhost:7880")
print("Room           : pitch-room")
print("Paste the token into the 'Custom' tab → Token field, then click Connect.\n")
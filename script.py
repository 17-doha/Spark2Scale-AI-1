# run in a python shell or script
from app.core.qdrant_client import get_qdrant
client = get_qdrant()
result = client.scroll("pitchdecks", with_payload=True)
for p in result[0]:
    print(p.id, p.payload)
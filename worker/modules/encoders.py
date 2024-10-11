from nodriver import cdp
from typing import Optional, Dict, Any

def encode_event(evt, fields: Dict[str, str]) -> Dict[str, Optional[Any]]:
    encoded = {}
    for key, attr in fields.items():
        value = getattr(evt, attr, None)
        encoded[key] = value.to_json() if value is not None and hasattr(value, 'to_json') else value
    return encoded

def RequestEncoder(evt: cdp.network.RequestWillBeSent) -> Dict[str, Optional[Any]]:
    fields = {
        'request': 'request',
        'request_id': 'request_id',
        'loader_id': 'loader_id',
        'document_url': 'document_url',
        'timestamp': 'timestamp',
        'wall_time': 'wall_time',
        'initiator': 'initiator',
        'redirect_has_extra_info': 'redirect_has_extra_info',
        'redirect_response': 'redirect_response',
        'type': 'type_',
        'frame_id': 'frame_id',
        'has_user_gesture': 'has_user_gesture'
    }
    return encode_event(evt, fields)

def ResponseEncoder(evt: cdp.network.ResponseReceived) -> Dict[str, Optional[Any]]:
    fields = {
        'response': 'response',
        'request_id': 'request_id',
        'loader_id': 'loader_id',
        'timestamp': 'timestamp',
        'type': 'type_',
        'has_extra_info': 'has_extra_info',
        'frame_id': 'frame_id'
    }
    return encode_event(evt, fields)

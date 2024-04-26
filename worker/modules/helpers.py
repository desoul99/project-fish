def RequestEncoder(event):
    request = {}
    request['request'] = event.request.to_json() if event.request is not None else None
    request['request_id'] = event.request_id.to_json() if event.request_id is not None else None
    request['loader_id'] = event.loader_id.to_json() if event.loader_id is not None else None
    request['document_url'] = event.document_url if event.document_url is not None else None
    request['timestamp'] = event.timestamp.to_json() if event.timestamp is not None else None
    request['wall_time'] = event.wall_time.to_json() if event.wall_time is not None else None
    request['initiator'] = event.initiator.to_json() if event.initiator is not None else None
    request['redirect_has_extra_info'] = event.redirect_has_extra_info if event.redirect_has_extra_info is not None else None
    request['redirect_response'] = event.redirect_response.to_json() if event.redirect_response is not None else None
    request['type'] = event.type_.to_json() if event.type_ is not None else None
    request['frame_id'] = event.frame_id.to_json() if event.frame_id is not None else None
    request['has_user_gesture'] = event.has_user_gesture if event.has_user_gesture is not None else None
    return request


def ResponseEncoder(event):
    response = {}
    response['response'] = event.response.to_json() if event.response is not None else None
    response['request_id'] = event.request_id.to_json() if event.request_id is not None else None
    response['loader_id'] = event.loader_id.to_json() if event.loader_id is not None else None
    response['timestamp'] = event.timestamp.to_json() if event.timestamp is not None else None
    response['type'] = event.type_.to_json() if event.type_ is not None else None
    response['has_extra_info'] = event.has_extra_info if event.has_extra_info is not None else None
    response['frame_id'] = event.frame_id.to_json() if event.frame_id is not None else None
    return response


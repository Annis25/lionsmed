from apps.editorial.publication import publish_content

def publish_event(*,actor,event):
    return publish_content(actor=actor,obj=event,kind="event")

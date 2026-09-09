from apps.editorial.publication import publish_content

def publish_action(*,actor,action):
    return publish_content(actor=actor,obj=action,kind="action")

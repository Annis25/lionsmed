from apps.editorial.publication import publish_content

def publish_news(*,actor,news):
    return publish_content(actor=actor,obj=news,kind="news")

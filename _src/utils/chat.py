def add_new_chat(chat_id: int) -> None:
    """Добавляет новый чат в список каналов."""
    with open("channels.txt", "r", encoding="utf-8") as r:
        channels = r.read().splitlines()

    channel_id = str(chat_id)
    if channel_id not in channels:
        with open("channels.txt", "a", encoding="utf-8") as w:
            if channel_id.startswith("-"):
                w.write(f"{channel_id}\n")

from datetime import datetime, timedelta
from telethon import TelegramClient, types
from telethon.tl.functions.messages import UpdateDialogFilterRequest, GetDialogFiltersRequest
from telethon.tl.types import DialogFilter, InputPeerChannel, TextWithEntities
from config import API_ID, API_HASH
from more_itertools import chunked


async def create_invite_folder(channels: list[str], user_id: int) -> str:
    session_file = f"session_{user_id}.session"
    client = TelegramClient(session_file, API_ID, API_HASH)

    await client.connect()
    if not await client.is_user_authorized():
        raise Exception("Не авторизован")

    filters = await client(GetDialogFiltersRequest())
    base_name = f"PANDA {(datetime.now() + timedelta(days=1)).strftime('%d.%m')}"
    created_folders = []

    for i, chunk in enumerate(chunked(channels, 200), 1):
        input_peers = []
        for ch in chunk:
            try:
                entity = await client.get_entity(ch)
                if isinstance(entity, types.Channel):
                    input_peers.append(InputPeerChannel(entity.id, entity.access_hash))
            except Exception:
                continue

        if not input_peers:
            continue

        new_id = max((f.id for f in filters.filters if hasattr(f, "id")), default=0) + i
        name = f"{base_name} ({i})" if len(channels) > 200 else base_name

        new_filter = DialogFilter(
            id=new_id,
            title=TextWithEntities(text=name, entities=[]),
            pinned_peers=[],
            include_peers=input_peers,
            exclude_peers=[],
            contacts=False,
            non_contacts=False,
            groups=False,
            broadcasts=False,
            bots=False,
            exclude_muted=False,
            exclude_read=False,
            exclude_archived=False
        )

        await client(UpdateDialogFilterRequest(id=new_id, filter=new_filter))
        created_folders.append(name)

    await client.disconnect()

    if not created_folders:
        return "❌ Не удалось создать ни одной папки"
    if len(created_folders) == 1:
        return f"✅ Папка '{created_folders[0]}' создана"
    return "✅ Созданы папки:\n" + "\n".join(f"• {name}" for name in created_folders)


from app.models.article import Article
from app.cache import get_or_load, delete


async def _load_categories():
    raw = await Article.distinct("category")

    flat = set()

    for item in raw:
        if not item:
            continue

        if isinstance(item, list):
            for value in item:
                if value and isinstance(value, str):
                    flat.add(value.strip())
        elif isinstance(item, str):
            flat.add(item.strip())

    return sorted(flat)


async def get_categories():
    return await get_or_load(
        key="categories",
        loader=_load_categories,
        ttl=300,
    )


async def reset_categories():
    await delete("categories")

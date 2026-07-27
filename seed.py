"""Seed demo data so the app has something to show on first run.

Run once, from the project root, with your venv active:

    python seed.py

Idempotent: each block is skipped if that table already has rows, so running it
twice is safe. Replace the placeholder URLs with real objects you've uploaded to
R2 under templates/.
"""
from app.database import SessionLocal
from app.models import Category, FeedPost, Template

db = SessionLocal()

try:
    # ---------------------------------------------------------------- catalog
    # (v1 template flow: categories + templates)
    if not db.query(Category).count():
        portraits = Category(
            name="Portraits",
            slug="portraits",
            image_url="https://placehold.co/400x400?text=Portraits",
        )
        anime = Category(
            name="Anime",
            slug="anime",
            image_url="https://placehold.co/400x400?text=Anime",
        )
        db.add_all([portraits, anime])
        db.commit()

        db.add_all([
            Template(
                category_id=portraits.id,
                name="Golden Hour",
                slug="golden-hour",
                description="Warm cinematic portrait style",
                thumbnail_url="https://placehold.co/300x300?text=Golden",
                original_image_url="https://placehold.co/1024x1024?text=Golden",
                ai_prompt="cinematic golden hour portrait, warm rim light, 85mm",
                sort_order=1,
            ),
            Template(
                category_id=anime.id,
                name="Anime Hero",
                slug="anime-hero",
                description="Turn your photo into an anime hero",
                thumbnail_url="https://placehold.co/300x300?text=Anime",
                original_image_url="https://placehold.co/1024x1024?text=Anime",
                ai_prompt="anime style hero portrait, clean line art, vibrant colors",
                sort_order=1,
            ),
        ])
        db.commit()
        print("seeded catalog (categories + templates).")
    else:
        print("catalog already seeded, skipping.")

    # ------------------------------------------------------------------- feed
    # (mobile app "For you" suggestion cards)
    if not db.query(FeedPost).count():
        db.add_all([
            FeedPost(
                title="Neon Cyberpunk City",
                prompt="Cyberpunk city, neon lights, rainy night, cinematic, 8k",
                media_type="image",
                model_name="happy-horse-1.1",
                author="sssimg",
                media_url="https://placehold.co/800x1000?text=Cyberpunk",
                thumb_url="https://placehold.co/400x500?text=Cyberpunk",
                sort_order=1,
            ),
            FeedPost(
                title="Ocean Drone Shot",
                prompt="Aerial drone shot flying over turquoise ocean waves at sunset",
                media_type="video",
                model_name="veo-3.1-fast",
                author="sssimg",
                media_url="https://placehold.co/800x450?text=Video",
                thumb_url="https://placehold.co/400x225?text=Video",
                sort_order=2,
            ),
        ])
        db.commit()
        print("seeded feed posts.")
    else:
        print("feed already seeded, skipping.")

finally:
    db.close()
    
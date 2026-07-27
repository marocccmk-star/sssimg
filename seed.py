"""Quick seed: two categories + two templates so the app has something to show.
Run once:  python seed.py
Replace the placeholder URLs with real R2 objects under templates/.
"""
from app.database import SessionLocal
<<<<<<< HEAD
from app.models import Category, FeedPost, Template
=======
from app.models import Category, Template
>>>>>>> origin/main

db = SessionLocal()
if not db.query(Category).count():
    c1 = Category(name="Portraits", slug="portraits",
                  image_url="https://placehold.co/400x400?text=Portraits")
    c2 = Category(name="Anime", slug="anime",
                  image_url="https://placehold.co/400x400?text=Anime")
    db.add_all([c1, c2]); db.commit()
    db.add_all([
        Template(category_id=c1.id, name="Golden Hour", slug="golden-hour",
                 description="Warm cinematic portrait style",
                 thumbnail_url="https://placehold.co/300x300?text=Golden",
                 original_image_url="https://placehold.co/1024x1024?text=Golden",
                 ai_prompt="cinematic golden hour portrait, warm rim light, 85mm",
                 sort_order=1),
        Template(category_id=c2.id, name="Anime Hero", slug="anime-hero",
                 description="Turn your photo into an anime hero",
                 thumbnail_url="https://placehold.co/300x300?text=Anime",
                 original_image_url="https://placehold.co/1024x1024?text=Anime",
                 ai_prompt="anime style hero portrait, clean line art, vibrant colors",
                 sort_order=1),
    ])
    db.commit()
<<<<<<< HEAD
    print("seeded catalog.")
if not db.query(FeedPost).count():
    db.add_all([
        FeedPost(title="Neon Cyberpunk City",
                 prompt="Cyberpunk city, neon lights, rainy night, cinematic, 8k",
                 media_type="image", model_name="happy-horse-1.1", author="sssimg",
                 media_url="https://placehold.co/800x1000?text=Cyberpunk",
                 thumb_url="https://placehold.co/400x500?text=Cyberpunk", sort_order=1),
        FeedPost(title="Ocean Drone Shot",
                 prompt="Aerial drone shot flying over turquoise ocean waves at sunset",
                 media_type="video", model_name="veo-3.1-fast", author="sssimg",
                 media_url="https://placehold.co/800x450?text=Video",
                 thumb_url="https://placehold.co/400x225?text=Video", sort_order=2),
    ])
    db.commit()
    print("seeded feed.")
=======
    print("seeded.")
>>>>>>> origin/main
else:
    print("already seeded.")
db.close()

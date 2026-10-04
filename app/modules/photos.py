"""Module Photos — gestionnaire de photos personnelles auto-hébergé."""

from app.core.config import get_settings
from app.core.module_registry import BaseModule, ModuleInfo, ModuleStatus


class PhotosModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="photos",
            name="Photos",
            description="Galerie de photos personnelles, albums et recherche",
            icon="image",
            order=25,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/photos",
            component_path="Photos",
            required_permissions=["photos.view"],
            is_core=False,
        ))

    def get_navigation_items(self, user_permissions: list[str]):
        if not get_settings().PHOTO_ENABLED:
            return []
        if not super().has_required_permissions(user_permissions):
            return []
        children = [
            {
                "code": "photos-all",
                "name": "Toutes les photos",
                "icon": "image",
                "route": "/photos",
                "order": 0,
            },
            {
                "code": "photos-albums",
                "name": "Albums",
                "icon": "folder",
                "route": "/photos/albums",
                "order": 1,
            },
            {
                "code": "photos-people",
                "name": "Personnes",
                "icon": "users",
                "route": "/photos/people",
                "order": 2,
            },
            {
                "code": "photos-places",
                "name": "Lieux",
                "icon": "database",
                "route": "/photos/places",
                "order": 3,
            },
            {
                "code": "photos-favorites",
                "name": "Favoris",
                "icon": "sparkles",
                "route": "/photos/favorites",
                "order": 4,
            },
        ]
        return [{
            "code": self.info.code,
            "name": self.info.name,
            "icon": self.info.icon,
            "route": self.info.route_path,
            "order": self.info.order,
            "children": children,
        }]

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True




from pydantic import BaseModel, Field

from merino.curated_recommendations.corpus_backends.protocol import CorpusItem, SurfaceId
from merino.curated_recommendations.ml_backends.protocol import SimilarStoriesProtocol, SpindleBackendProtocol
from merino.configs import settings
from merino.utils.http_client import create_http_client

SIMILAR_STORIES_TEXT_API_PATH = "/find_similar_stories"
SIMILAR_STORIES_IMAGE_API_PATH = "/find_similar_images"

LANGUAGE_FOR_SURFACE = {SurfaceId.NEW_TAB_EN_GB: "en", SurfaceId.NEW_TAB_EN_CA: "en", SurfaceId.NEW_TAB_EN_IE: "en",
                      SurfaceId.NEW_TAB_EN_US: "en"}


class SimilarStoriesTextItem(BaseModel):
    corpus_item_id: str
    title: str
    excerpt: str

class SimilarStoriesImageItem(BaseModel):
    corpus_item_id: str
    url: str


class FindSimilarArticlesRequest(BaseModel):
    items: list[SimilarStoriesTextItem]
    threshold: float = Field(0.85, ge=0.0, le=1.0)
    language: str = Field("en", min_length=2, max_length=10)


class FindSimilarResponse(BaseModel):
    similar: dict[str, list[str]]
    model_version: str
    threshold: float
    language: str
    num_items: int
    num_pairs: int



class SimilarStoriesInfo(SimilarStoriesProtocol):
    def __init__(self, keys):
        self.keys = list(keys)
        self.idx = {k: i for i, k in enumerate(self.keys)}

        # store only upper-triangular "on" entries
        self._edges = set()

    def _normalize(self, a, b):
        i = self.idx[a]
        j = self.idx[b]

        if i > j:
            i, j = j, i

        return (i, j)

    def set(self, a, b, value=True):
        key = self._normalize(a, b)

        if value:
            self._edges.add(key)
        else:
            self._edges.discard(key)

    def get(self, a, b):
        return self._normalize(a, b) in self._edges

    def remove(self, a, b):
        self.set(a, b, False)

    def clear(self):
        self._edges.clear()

    def neighbors(self, a):
        """ Returns list of items that match item"""
        i = self.idx[a]
        out = []
        for x, y in self._edges:
            if x == i:
                out.append(self.keys[y])
            elif y == i:
                out.append(self.keys[x])
        return out

    def __contains__(self, pair):
        a, b = pair
        return self.get(a, b)

    def __len__(self):
        return len(self._edges)

    def __repr__(self):
        return f"SparseTriMatrix(num_keys={len(self.keys)}, num_edges={len(self)})"



class SpindleBackend(SpindleBackendProtocol):
    """Connects to the Content-ML Spindle service.
    """

    def __init__(self, base_url:str, request_timeout:int):
        super().__init__()
        self.client = create_http_client(base_url=, request_timeout=settings.spindle.api.request_wait_seconds, max_connections=5)
        self.text_info= dict[SurfaceId, SimilarStoriesInfo] = {}
        self.image_info = dict[SurfaceId, SimilarStoriesInfo] = {}

    def _language_for_surface(self, surface: SurfaceId) -> str | None:
        return LANGUAGE_FOR_SURFACE.get(surface, None)

    def _is_surface_supported(self, surface: SurfaceId) -> bool:
        return self._language_for_surface(surface) is not None

    def refresh_duplicate_item_info(self, items: list[CorpusItem], surface: SurfaceId, threshold: float=0.85):
        """ Make best effort to find duplicate stories based on embeddings and store in cache"""
        if not self._is_surface_supported(surface):
            return
        ## TODO Populate SimilarStoriesInfo from calling SIMILAR_STORIES_TEXT_API_PATH


    def get_similar_stories_text(self, surface: SurfaceId) -> SimilarStoriesInfo | None:
        """ Get similar stories based on text """
        return self.text_info.get(surface, None)

    def get_similar_stories_image(self, surface: SurfaceId) -> SimilarStoriesInfo | None:
        """ Get similar stories based on image similarity """
        return self.image_info.get(surface, None)

class DummySpindleBackend(SpindleBackendProtocol):
    def refresh_duplicate_item_info(self, items: list[CorpusItem], surface: SurfaceId, threshold: float=0.85):
        return

    def get_similar_stories_text(self, corpus_item_id:str, surface: SurfaceId) -> SimilarStoriesInfo | None:
        return None

    def get_similar_stories_image(self, corpus_item_id:str, surface: SurfaceId) -> SimilarStoriesInfo | None:
        return None

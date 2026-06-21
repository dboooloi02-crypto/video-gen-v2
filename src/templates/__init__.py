from templates.base             import BaseTemplate
from templates.english_learning import EnglishLearningTemplate
from templates.podcast          import PodcastTemplate
from templates.tiktok           import TikTokTemplate
from templates.mixed_inline     import MixedInlineTemplate

REGISTRY = {
    "english_learning": EnglishLearningTemplate,
    "english":          EnglishLearningTemplate,
    "el":               EnglishLearningTemplate,
    "podcast":          PodcastTemplate,
    "tiktok":           TikTokTemplate,
    "tt":               TikTokTemplate,
    "mixed_inline":     MixedInlineTemplate,
    "mixed":            MixedInlineTemplate,
}

def get_template(name: str) -> BaseTemplate:
    cls = REGISTRY.get(name.lower().strip())
    if cls is None:
        available = ", ".join(sorted({v.__name__ for v in REGISTRY.values()}))
        raise ValueError(f"Unknown template '{name}'. Available: {available}")
    return cls()

def list_templates():
    seen, out = set(), []
    for cls in REGISTRY.values():
        inst = cls()
        if inst.name not in seen:
            out.append(inst.name)
            seen.add(inst.name)
    return sorted(out)

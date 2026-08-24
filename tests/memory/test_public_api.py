import commercial_reasoner.memory as memory


def test_public_api_exports_loader_and_llm_type_achado_i4():
    # Quem integra de fora precisa dos dois: o loader (unica forma de construir
    # CanonicalFacts a partir de arquivo) e o tipo do callable de LLM.
    assert "load_canonical_facts" in memory.__all__
    assert "LLMExtractFn" in memory.__all__
    assert memory.load_canonical_facts is not None
    assert memory.LLMExtractFn is not None


def test_all_exported_names_are_importable():
    for name in memory.__all__:
        assert hasattr(memory, name), name

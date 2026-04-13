import pytest
from gasp.app.sim.genome_codec import (
    encode_unit, decode_unit, encode_genome, decode_genome,
    make_random_genome, make_behavior_program_snippet, validate_unit
)
from gasp.app.sim.genetics import Unit, Promoter
from gasp.app.sim.constants import ActionType, SignalId, CompareOp
from gasp.app.util.rng import RNG

def make_sample_unit():
    p = Promoter(signal_id=SignalId.ENERGY, compare_op=CompareOp.GT,
                  threshold=50.0, base_strength=1.5)
    return Unit(promoter=p, target_type='gene', gene=ActionType.MOVE, module_id=None,
                source_state=1, next_state=2)

def test_encode_decode_roundtrip():
    unit = make_sample_unit()
    d = encode_unit(unit)
    unit2 = decode_unit(d)
    assert unit2.promoter.signal_id == unit.promoter.signal_id
    assert unit2.promoter.compare_op == unit.promoter.compare_op
    assert unit2.promoter.threshold == unit.promoter.threshold
    assert unit2.gene == unit.gene
    assert unit2.target_type == unit.target_type
    assert unit2.source_state == unit.source_state
    assert unit2.next_state == unit.next_state

def test_genome_encode_decode_roundtrip():
    rng = RNG(123)
    genome = make_random_genome(rng, 10)
    encoded = encode_genome(genome)
    decoded = decode_genome(encoded)
    assert len(decoded) == len(genome)
    for orig, dec in zip(genome, decoded):
        assert orig.promoter.signal_id == dec.promoter.signal_id
        assert orig.target_type == dec.target_type

def test_make_random_genome_valid():
    rng = RNG(42)
    genome = make_random_genome(rng, 8)
    assert len(genome) == 8
    assert any(unit.source_state is not None for unit in genome)
    assert any(unit.next_state is not None for unit in genome)
    for unit in genome:
        assert isinstance(unit.promoter.signal_id, SignalId)
        assert isinstance(unit.promoter.compare_op, CompareOp)
        if unit.target_type == 'gene':
            assert isinstance(unit.gene, ActionType)
        elif unit.target_type == 'module':
            from gasp.app.sim.genetics import DEFAULT_MODULES
            assert unit.module_id in DEFAULT_MODULES

def test_make_random_genome_respects_requested_length_for_small_genomes():
    rng = RNG(7)
    genome = make_random_genome(rng, 1)
    assert len(genome) == 1
    assert genome[0].gene == ActionType.MOVE
    assert genome[0].promoter.signal_id == SignalId.CAN_MOVE

def test_make_random_genome_respects_param_state_count():
    from gasp.app.persistence.params_io import Parameters

    rng = RNG(5)
    genome = make_random_genome(rng, 12, params=Parameters(internal_state_count=2))

    for unit in genome:
        if unit.source_state is not None:
            assert unit.source_state < 2
        if unit.next_state is not None:
            assert unit.next_state < 2

def test_make_behavior_program_snippet_respects_state_budget():
    from gasp.app.persistence.params_io import Parameters

    snippet = make_behavior_program_snippet(RNG(8), params=Parameters(internal_state_count=3))

    assert snippet
    assert any(unit.source_state is not None or unit.next_state is not None for unit in snippet)
    for unit in snippet:
        if unit.source_state is not None:
            assert unit.source_state < 3
        if unit.next_state is not None:
            assert unit.next_state < 3

def test_validate_unit_clamps_state_indices():
    unit = validate_unit(Unit(
        promoter=Promoter(signal_id=SignalId.ENERGY, compare_op=CompareOp.GT, threshold=1.0, base_strength=1.0),
        target_type='gene',
        gene=ActionType.MOVE,
        source_state=-4,
        next_state=99,
    ))

    assert unit.source_state == 0
    assert unit.next_state == 7

def test_validate_unit_respects_custom_state_count():
    unit = validate_unit(Unit(
        promoter=Promoter(signal_id=SignalId.ENERGY, compare_op=CompareOp.GT, threshold=1.0, base_strength=1.0),
        target_type='gene',
        gene=ActionType.MOVE,
        source_state=3,
        next_state=8,
    ), state_count=2)

    assert unit.source_state == 1
    assert unit.next_state == 1

def test_decode_unit_never_crashes():
    # Test with various garbage inputs
    garbage_inputs = [
        {},
        None,
        "not a dict",
        {'promoter': 'bad'},
        {'promoter': {'signal_id': 'INVALID', 'compare_op': 'BAD'}},
        {'gene': 'NONEXISTENT'},
        42,
        [],
        {'promoter': {}, 'gene': None, 'target_type': 'gene'},
    ]
    for garbage in garbage_inputs:
        try:
            result = decode_unit(garbage)
            # Should return a valid Unit
            assert isinstance(result, Unit)
        except Exception as e:
            pytest.fail(f"decode_unit crashed on input {garbage!r}: {e}")

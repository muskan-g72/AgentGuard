import pytest

from guard.intent_gap import apply_answers, find_gaps
from guard.scenarios import CONTRACT


KEYS = ["refundable", "seat_confirmed", "baggage"]


def test_omitted_preferences_return_exact_three_fixed_questions():
    questions = find_gaps(CONTRACT, "Book the cheapest train to Delhi")
    assert [q["key"] for q in questions] == KEYS
    assert [q["text"] for q in questions] == [
        "Must the ticket be refundable?", "Must the ticket have a confirmed seat?", "Must baggage be included?",
    ]
    assert all(q["options"] == ["yes", "no", "don't care"] for q in questions)


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("answer", ["yes", "no"])
def test_already_known_preferences_do_not_get_questions(key, answer):
    draft = apply_answers(CONTRACT, {key: answer})
    assert key not in [q["key"] for q in find_gaps(draft, "Book a train")]


@pytest.mark.parametrize("key,sentence", [
    ("refundable", "Book a refundable ticket"),
    ("refundable", "A non-refundable fare is fine"),
    ("refundable", "I do not need a refund"),
    ("seat_confirmed", "I need a confirmed seat"),
    ("seat_confirmed", "A waitlisted ticket is fine"),
    ("baggage", "Include baggage"),
    ("baggage", "No luggage needed"),
])
def test_explicit_sentence_preference_is_not_asked_again(key, sentence):
    assert key not in [q["key"] for q in find_gaps(CONTRACT, sentence)]


@pytest.mark.parametrize("sentence", [
    "Book the cheapest ticket", "Book a train; is it refundable?",
    "I am not sure whether I need baggage", "Maybe a confirmed seat",
])
def test_price_or_uncertainty_never_implies_a_requirement(sentence):
    assert [q["key"] for q in find_gaps(CONTRACT, sentence)] == KEYS


def test_only_unspecified_fields_are_asked_and_order_is_stable():
    draft = apply_answers(CONTRACT, {"seat_confirmed": "yes"})
    assert [q["key"] for q in find_gaps(draft, "Include baggage")] == ["refundable"]


def test_apply_answers_maps_values_without_mutating_draft_or_other_fields():
    before = CONTRACT.model_dump()
    result = apply_answers(CONTRACT, dict(zip(KEYS, ["yes", "no", "don't care"])))
    assert result.requirements.model_dump() == dict(zip(KEYS, [True, False, None]))
    assert result.model_dump(exclude={"requirements"}) == CONTRACT.model_dump(exclude={"requirements"})
    assert CONTRACT.model_dump() == before


def test_dont_care_can_clear_a_requirement():
    draft = apply_answers(CONTRACT, {"refundable": "yes"})
    assert apply_answers(draft, {"refundable": "don't care"}).requirements.refundable is None


@pytest.mark.parametrize("answers", [
    {"max_total": "yes"}, {"refundable": "maybe"}, {"baggage": True}, {"baggage": None}, [],
])
def test_invalid_answers_fail_without_changing_the_draft(answers):
    before = CONTRACT.model_dump()
    with pytest.raises(ValueError):
        apply_answers(CONTRACT, answers)
    assert CONTRACT.model_dump() == before


def test_dictionary_drafts_are_supported_and_options_are_not_shared():
    questions = find_gaps(CONTRACT.model_dump(), "book a train")
    questions[0]["options"].clear()
    assert find_gaps(CONTRACT, "book a train")[0]["options"] == ["yes", "no", "don't care"]
    assert apply_answers(CONTRACT.model_dump(), {}).model_dump() == CONTRACT.model_dump()

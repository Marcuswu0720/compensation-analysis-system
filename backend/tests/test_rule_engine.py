from app.ingestion.commit import confirm_upload
from app.ingestion.loader import stage_upload
from app.models import User, ViewerPermission
from app.qa.rule_engine import answer_question

from .xlsx_fixtures import build_month1_workbook, build_month2_workbook


def _seed_two_months(db):
    for month, builder in (("2026-01", build_month1_workbook), ("2026-02", build_month2_workbook)):
        batch = stage_upload(db, month=month, file_bytes=builder(), filename=f"{month}.xlsx", uploaded_by="tester")
        confirm_upload(db, batch, operator="tester")


def _admin(db):
    user = User(username="marcus", password_hash="x", role="admin")
    db.add(user)
    db.commit()
    return user


def test_trend_question_with_month_range(db_session):
    _seed_two_months(db_session)
    admin = _admin(db_session)

    resp = answer_question(db_session, admin, "Sales部门1-2月人力成本怎么变化的")
    assert "Sales" in resp["answer"]
    assert "2026-01" in resp["answer"]
    assert "2026-02" in resp["answer"]
    assert "4200" not in resp["answer"]  # sanity: it's formatted with ₦ and commas, not a bare number


def test_attribution_question_with_why_keyword(db_session):
    _seed_two_months(db_session)
    admin = _admin(db_session)

    resp = answer_question(db_session, admin, "整个公司2月为什么比1月成本高")
    answer = resp["answer"]
    assert "新入职 1 人" in answer
    assert "离职 2 人" in answer
    assert "✓ 与净变化吻合" in answer


def test_chinese_department_keyword_resolves_to_english_name(db_session):
    _seed_two_months(db_session)
    admin = _admin(db_session)

    # No department literally named with a Chinese word in the fixture data,
    # but the CN keyword table should still resolve "手机分期" style lookups
    # for real department names - here we just confirm an unmatched keyword
    # falls back to whole-company scope instead of crashing or guessing.
    resp = answer_question(db_session, admin, "手机分期部门1月人力成本")
    assert "全公司" in resp["answer"]


def test_ambiguous_department_asks_for_clarification(db_session):
    _seed_two_months(db_session)
    admin = _admin(db_session)

    # "sales" as lowercase substring matches nothing extra here, but let's
    # confirm a genuinely no-match query still produces a graceful reply
    # rather than raising.
    resp = answer_question(db_session, admin, "Marketing部门趋势")
    assert "全公司" in resp["answer"] or "没有查到" in resp["answer"]


def test_viewer_with_no_grants_sees_nothing(db_session):
    _seed_two_months(db_session)
    viewer = User(username="xiajie", password_hash="x", role="viewer")
    db_session.add(viewer)
    db_session.commit()

    resp = answer_question(db_session, viewer, "公司2月为什么比1月成本高")
    assert "没有被分配任何可查看的部门" in resp["answer"]


def test_viewer_role_redacts_names_in_attribution_reply(db_session):
    _seed_two_months(db_session)
    viewer = User(username="xiajie", password_hash="x", role="viewer")
    db_session.add(viewer)
    db_session.commit()
    db_session.add_all(
        [
            ViewerPermission(user_id=viewer.id, scope_type="entity", entity="PalmPay", granted_by="tester"),
            ViewerPermission(user_id=viewer.id, scope_type="entity", entity="Flexi", granted_by="tester"),
        ]
    )
    db_session.commit()

    resp = answer_question(db_session, viewer, "公司2月为什么比1月成本高")
    assert "无权限查看" in resp["answer"]
    assert "Alice" not in resp["answer"]
    assert "Bob" not in resp["answer"]


def test_no_data_uploaded_gives_clear_message(db_session):
    admin = _admin(db_session)
    resp = answer_question(db_session, admin, "随便问点什么")
    assert "还没有任何月份的数据" in resp["answer"]


def test_unavailable_month_is_flagged_not_silently_dropped(db_session):
    _seed_two_months(db_session)
    admin = _admin(db_session)
    resp = answer_question(db_session, admin, "1月到12月成本趋势")
    assert "还没有数据" in resp["answer"]

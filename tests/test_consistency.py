import logging

import pytest

from stylemate.consistency import (
    PlanRejected,
    build_image_prompt,
    diversity_issues,
    plan_issues,
    preference_issues,
)
from stylemate.diagnostics import new_request_id, trace
from stylemate.models import GarmentAnalysis, Outfit, OutfitPlan
from stylemate.operations import BusyError, OperationGate
from stylemate.runtime import safe_connection_error


def garment() -> GarmentAnalysis:
    return GarmentAnalysis(
        category="上装", subcategory="短款皮夹克", color="深棕色", material="皮革",
        pattern="无", fit="修身", seasons=["秋季"], styles=["美式复古"],
        preservation_notes=["做旧金属拉链"],
    )


def outfit(**overrides) -> Outfit:
    values = dict(
        id="look-1", style="美式复古", top="深棕色短款皮夹克", outerwear="无",
        bottom="直筒牛仔裤", shoes="白色帆布鞋", bag="棕色邮差包",
        accessories=["银色项链"], reason="色彩协调", compatibility_score=88,
        image_prompt="pair with relaxed denim",
    )
    values.update(overrides)
    return Outfit(**values)


def test_image_prompt_is_built_from_structured_pieces():
    prompt = build_image_prompt(garment(), outfit())
    assert "深棕色短款皮夹克" in prompt
    assert "直筒牛仔裤" in prompt
    assert "白色帆布鞋" in prompt
    assert "棕色邮差包" in prompt
    assert "银色项链" in prompt
    assert "做旧金属拉链" in prompt
    # 外套为“无”时不应出现在清单里
    assert "outer layer" not in prompt
    assert "top-down fashion flat-lay" in prompt


def test_freeform_image_prompt_cannot_override_piece_list():
    prompt = build_image_prompt(garment(), outfit(image_prompt="replace denim with a red skirt"))
    assert "red skirt" not in prompt
    assert "直筒牛仔裤" in prompt


def test_duplicate_model_ids_are_rejected_before_rendering():
    plan = OutfitPlan(outfits=[outfit(), outfit(), outfit(id="look-3")])
    assert any("编号" in issue for issue in plan_issues(plan))


def test_diagnostics_drop_unknown_fields_and_newlines():
    from stylemate.diagnostics import _details
    output = _details({"api_image_key": "sensitive", "url": "https://private.example/key",
                       "status": "completed\nforged-log", "retries": 2})
    assert "sensitive" not in output and "private.example" not in output
    assert "\n" not in output and "retries=2" in output


def test_image_prompt_ignores_missing_optional_pieces():
    prompt = build_image_prompt(garment(), outfit(bag="", accessories=[]))
    assert "bag" not in prompt
    assert "accessories" not in prompt


def test_image_prompt_requires_at_least_one_piece():
    with pytest.raises(ValueError):
        build_image_prompt(garment(), outfit(top="", bottom="", shoes="", bag="",
                                             outerwear="", accessories=[]))


def test_plan_issues_flags_missing_required_fields():
    issues = plan_issues(OutfitPlan(outfits=[
        outfit(), outfit(id="look-2", shoes="  "), outfit(id="look-3", reason=""),
    ]))
    assert issues == ["LOOK 02 缺少鞋子", "LOOK 03 缺少搭配理由"]


def test_plan_issues_passes_a_complete_plan():
    assert plan_issues(OutfitPlan(outfits=[outfit(), outfit(id="look-2"), outfit(id="look-3")])) == []


def test_diversity_issues_flag_near_duplicate_looks():
    clone = outfit(id="look-2", style="另一风格", reason="稍有不同", compatibility_score=80)
    distinct = outfit(id="look-3", bottom="工装短裤", shoes="厚底运动鞋", bag="斜挎包",
                      outerwear="牛仔外套", reason="更街头", compatibility_score=79)
    plan = OutfitPlan(outfits=[outfit(), clone, distinct])
    issues = diversity_issues(plan, garment())
    assert issues == ["LOOK 01 与 LOOK 02 过于相似，差异度不足"]


def test_diversity_ignores_original_garment_and_placeholder_wu():
    # 原单品（top）每套都在、外套都是“无”，其余单品不同 → 不算重复
    looks = [
        outfit(),
        outfit(id="look-2", bottom="西装直筒裤", shoes="黑色乐福鞋", bag="托特包"),
        outfit(id="look-3", bottom="工装短裤", shoes="厚底运动鞋", bag="腰包"),
    ]
    assert diversity_issues(OutfitPlan(outfits=looks), garment()) == []


def test_diversity_compares_tops_when_original_item_is_a_bottom():
    from stylemate.consistency import diversity_pair_issues
    trousers = garment().model_copy(update={"subcategory": "直筒裤", "color": "黑色"})
    first = outfit(top="白衬衫", bottom="黑色直筒裤", bag="无", outerwear="无")
    second = outfit(id="other", top="白衬衫", bottom="黑色直筒裤", bag="无", outerwear="无")
    assert diversity_pair_issues(first, second, 1, 2, trousers)


def test_diversity_ignores_garment_when_it_lives_in_outerwear():
    # Demo 场景：原单品出现在外套字段，三套共享它也不算重复
    jacket = "用户的黑色短款皮夹克"
    looks = [
        outfit(outerwear=jacket),
        outfit(id="look-2", outerwear=jacket, bottom="水洗牛仔裤", shoes="复古跑鞋", bag="斜挎包"),
        outfit(id="look-3", outerwear=jacket, bottom="工装裤", shoes="工装靴", bag="托特包"),
    ]
    assert diversity_issues(OutfitPlan(outfits=looks), garment()) == []
    # 除共享的原单品外套外，还有两件主要单品相同 → 判定重复
    similar = outfit(id="look-2", outerwear=jacket, bottom="直筒牛仔裤", bag="棕色邮差包")
    third = outfit(id="look-3", outerwear=jacket, bottom="工装裤", shoes="工装靴", bag="托特包")
    issues = diversity_issues(OutfitPlan(outfits=[outfit(outerwear=jacket), similar, third]),
                              garment())
    assert issues == ["LOOK 01 与 LOOK 02 过于相似，差异度不足"]


def test_diversity_issues_pass_distinct_looks():
    varied = OutfitPlan(outfits=[
        outfit(),
        outfit(id="look-2", bottom="阔腿西装裤", shoes="黑色乐福鞋", bag="托特包",
               outerwear="风衣", reason="更利落的轮廓", compatibility_score=82),
        outfit(id="look-3", bottom="工装短裤", shoes="厚底运动鞋", bag="斜挎包",
               outerwear="牛仔外套", reason="更街头", compatibility_score=79),
    ])
    assert diversity_issues(varied) == []


def test_preference_issues_enforce_banned_items():
    plan = OutfitPlan(outfits=[outfit(), outfit(id="look-2"), outfit(id="look-3", shoes="裸色高跟鞋")])
    assert preference_issues(plan, ["高跟鞋", "紧身裤"]) == ["LOOK 03 包含禁用单品「高跟鞋」"]
    assert preference_issues(plan, []) == []


def test_plan_rejection_message_passes_through_untouched():
    error = PlanRejected("搭配方案未通过校验（LOOK 02 缺少鞋子），请重新生成。")
    assert safe_connection_error(error) == str(error)
    assert "请重新生成" in safe_connection_error(error)


def test_error_classifier_distinguishes_model_and_quota_codes():
    model_error = RuntimeError("private detail")
    model_error.status_code = 404
    model_error.body = {"code": "model_not_found"}
    message = safe_connection_error(model_error)
    assert "模型不存在" in message and "private" not in message

    quota_error = RuntimeError("private detail")
    quota_error.status_code = 429
    quota_error.body = {"code": "insufficient_quota"}
    assert "余额或额度不足" in safe_connection_error(quota_error)

    timeout_error = RuntimeError("private detail")
    timeout_error.status_code = 408
    assert "超时" in safe_connection_error(timeout_error)


def test_trace_logs_safe_fields_only(caplog):
    logger = logging.getLogger("stylemate.requests")
    # 诊断日志必须真实输出：INFO 级别可用，且挂了实际的输出 handler
    assert logger.isEnabledFor(logging.INFO)
    assert any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers)
    request_id = new_request_id()
    assert len(request_id) == 12 and request_id.isalnum()
    with caplog.at_level(logging.DEBUG, logger="stylemate.requests"):
        with trace(request_id, "analyze", model="gpt-x", protocol="responses", api_key="sk-secret"):
            pass
        with pytest.raises(RuntimeError):
            with trace(request_id, "image", model="img", protocol="openai_edits"):
                raise RuntimeError("provider said: sk-secret leaked")
    assert "req=" in caplog.text and "event=done" in caplog.text
    assert "event=failed" in caplog.text
    assert "sk-secret" not in caplog.text
    assert "provider said" not in caplog.text


def test_gate_scopes_rate_limit_independently():
    now = [0]
    gate = OperationGate(cooldown=10, clock=lambda: now[0])
    with gate.claim("session-a", "secret", scope="identify"):
        # 同一会话紧接着进入下一步生成流程，不应被识别步骤的冷却时间挡住
        with gate.claim("session-a", "secret", scope="generate"):
            pass
        with pytest.raises(BusyError):
            with gate.claim("session-a", "secret", scope="generate"):
                pass
        with pytest.raises(BusyError):
            with gate.claim("session-a", "secret", scope="identify"):
                pass
    now[0] = 11
    with gate.claim("session-a", "secret", scope="identify"):
        pass

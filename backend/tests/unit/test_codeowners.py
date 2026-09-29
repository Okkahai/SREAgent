from opspilot.integrations.codeowners import owners_for, parse

RULES = parse(
    """
# comment
*                     @org/all
/demo/shop/           @org/shop-team
*.md                  @org/docs
/backend/**/db/*.py   @org/data @alice   # inline comment
"""
)


def test_last_match_wins_and_anchoring():
    assert owners_for(RULES, "web/app.tsx") == ["@org/all"]
    assert owners_for(RULES, "demo/shop/shop/checkout.py") == ["@org/shop-team"]
    assert owners_for(RULES, "docs/x.md") == ["@org/docs"]
    assert owners_for(RULES, "backend/src/opspilot/db/engine.py") == ["@org/data", "@alice"]
    assert owners_for(RULES, "backend/src/opspilot/db/sub/x.py") == ["@org/all"]

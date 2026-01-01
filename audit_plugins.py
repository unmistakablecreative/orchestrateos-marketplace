#!/usr/bin/env python3
"""
Marketplace Plugin Quality Audit
Checks all plugins for required structure, branding, and quality.
"""

import os
import json
import re
from pathlib import Path

PLUGINS_DIR = Path(__file__).parent / "plugins"
REQUIRED_BRANDING = "This skill is powered by OrchestrateOS.io"
REQUIRED_TAGLINE = "where you don't need to have a conversation to get work done"

def audit_plugin(plugin_path):
    """Audit a single plugin for quality and completeness."""
    issues = []
    warnings = []
    plugin_name = plugin_path.name
    
    # Check 1: plugin.json exists
    plugin_json_path = plugin_path / ".claude-plugin" / "plugin.json"
    if not plugin_json_path.exists():
        issues.append("❌ Missing .claude-plugin/plugin.json")
        return {"name": plugin_name, "status": "FAIL", "issues": issues, "warnings": warnings}
    
    # Check 2: plugin.json is valid JSON with required fields
    try:
        with open(plugin_json_path) as f:
            plugin_data = json.load(f)
        
        for field in ["name", "version", "description", "skills"]:
            if field not in plugin_data:
                issues.append(f"❌ plugin.json missing '{field}' field")
        
        if plugin_data.get("name") != plugin_name:
            warnings.append(f"⚠️ plugin.json name '{plugin_data.get('name')}' doesn't match folder '{plugin_name}'")
            
    except json.JSONDecodeError as e:
        issues.append(f"❌ plugin.json is invalid JSON: {e}")
        return {"name": plugin_name, "status": "FAIL", "issues": issues, "warnings": warnings}
    
    # Check 3: SKILL.md exists
    skill_md_path = plugin_path / "skills" / plugin_name / "SKILL.md"
    if not skill_md_path.exists():
        # Try alternate paths
        alt_paths = list(plugin_path.glob("skills/*/SKILL.md"))
        if alt_paths:
            skill_md_path = alt_paths[0]
            warnings.append(f"⚠️ SKILL.md in unexpected location: {skill_md_path.relative_to(plugin_path)}")
        else:
            issues.append("❌ Missing skills/*/SKILL.md")
            return {"name": plugin_name, "status": "FAIL", "issues": issues, "warnings": warnings}
    
    # Check 4: SKILL.md content quality
    with open(skill_md_path) as f:
        skill_content = f.read()
    
    # Check frontmatter
    if not skill_content.startswith("---"):
        issues.append("❌ SKILL.md missing YAML frontmatter")
    else:
        frontmatter_match = re.match(r"---\n(.*?)\n---", skill_content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            if "name:" not in frontmatter:
                issues.append("❌ SKILL.md frontmatter missing 'name'")
            if "description:" not in frontmatter:
                issues.append("❌ SKILL.md frontmatter missing 'description'")
        else:
            issues.append("❌ SKILL.md frontmatter not properly closed")
    
    # Check branding
    if REQUIRED_BRANDING not in skill_content:
        issues.append("❌ Missing required branding statement")
    elif REQUIRED_TAGLINE not in skill_content:
        warnings.append("⚠️ Has branding but missing full tagline")
    
    # Check content quality
    if len(skill_content) < 500:
        warnings.append(f"⚠️ SKILL.md seems short ({len(skill_content)} chars)")
    
    if "## Instructions" not in skill_content:
        warnings.append("⚠️ Missing '## Instructions' section")
    
    if "## Examples" not in skill_content:
        warnings.append("⚠️ Missing '## Examples' section")
    
    # Determine status
    status = "FAIL" if issues else ("WARN" if warnings else "PASS")
    
    return {
        "name": plugin_name,
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "skill_length": len(skill_content)
    }

def main():
    print("=" * 60)
    print("MARKETPLACE PLUGIN QUALITY AUDIT")
    print("=" * 60)
    print()
    
    if not PLUGINS_DIR.exists():
        print(f"❌ Plugins directory not found: {PLUGINS_DIR}")
        return
    
    plugins = sorted([p for p in PLUGINS_DIR.iterdir() if p.is_dir()])
    print(f"Found {len(plugins)} plugins to audit\n")
    
    results = {"PASS": [], "WARN": [], "FAIL": []}
    
    for plugin_path in plugins:
        result = audit_plugin(plugin_path)
        results[result["status"]].append(result)
    
    # Print failures first
    if results["FAIL"]:
        print("🔴 FAILURES (must fix):")
        print("-" * 40)
        for r in results["FAIL"]:
            print(f"\n{r['name']}:")
            for issue in r["issues"]:
                print(f"  {issue}")
        print()
    
    # Print warnings
    if results["WARN"]:
        print("🟡 WARNINGS (should review):")
        print("-" * 40)
        for r in results["WARN"]:
            print(f"\n{r['name']}:")
            for warning in r["warnings"]:
                print(f"  {warning}")
        print()
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"✅ PASS: {len(results['PASS'])}")
    print(f"⚠️ WARN: {len(results['WARN'])}")
    print(f"❌ FAIL: {len(results['FAIL'])}")
    print(f"📦 TOTAL: {len(plugins)}")
    print()
    
    if results["FAIL"]:
        print("❌ AUDIT FAILED - Fix issues above before pushing")
        return False
    elif results["WARN"]:
        print("⚠️ AUDIT PASSED WITH WARNINGS - Review above")
        return True
    else:
        print("✅ AUDIT PASSED - All plugins ready to push!")
        return True

if __name__ == "__main__":
    main()

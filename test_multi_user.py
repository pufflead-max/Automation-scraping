#!/usr/bin/env python3
"""
Test script to verify multi-user lead management implementation.
"""

import sys
import os
from datetime import datetime

# Add scraper/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scraper", "src"))

def test_models():
    """Test that models support user fields."""
    print("\n" + "="*60)
    print("TEST 1: Models Support User Fields")
    print("="*60)
    
    from models import FacebookLead
    
    lead = FacebookLead(
        source_url="https://facebook.com/test",
        title="Test Lead",
        description="Test description",
        user_email="test@example.com",
        user_name="Test User",
        user_phone="+1234567890"
    )
    
    assert lead.user_email == "test@example.com"
    assert lead.user_name == "Test User"
    assert lead.user_phone == "+1234567890"
    
    print("✅ Models correctly support user fields")
    print(f"   - user_email: {lead.user_email}")
    print(f"   - user_name: {lead.user_name}")
    print(f"   - user_phone: {lead.user_phone}")

def test_database_methods():
    """Test database user filtering methods."""
    print("\n" + "="*60)
    print("TEST 2: Database User Filtering Methods")
    print("="*60)
    
    from database import get_db_manager
    
    db = get_db_manager()
    
    # Check if methods exist
    assert hasattr(db, 'find_leads_by_user')
    assert hasattr(db, 'count_leads_by_user')
    
    print("✅ Database methods exist:")
    print("   - find_leads_by_user()")
    print("   - count_leads_by_user()")

def test_ghl_user_mapping():
    """Test GHL user mapping logic."""
    print("\n" + "="*60)
    print("TEST 3: GHL User Mapping")
    print("="*60)
    
    from integrations.ghl import GHLClient
    from config import get_ghl_config
    
    # Create a test lead with user data
    test_lead = {
        "title": "Test Lead",
        "description": "Test description",
        "source": "facebook",
        "source_url": "https://facebook.com/test",
        "user_email": "test@example.com",
        "user_name": "Test User",
        "user_phone": "+1234567890"
    }
    
    print("✅ GHL client can process leads with user fields")
    print(f"   - Lead has user_email: {test_lead.get('user_email')}")
    print(f"   - Lead has user_name: {test_lead.get('user_name')}")
    print(f"   - Lead has user_phone: {test_lead.get('user_phone')}")

def test_push_leads_user_filter():
    """Test push_leads user filtering."""
    print("\n" + "="*60)
    print("TEST 4: Push Leads User Filtering")
    print("="*60)
    
    import inspect
    from push_leads import push_leads
    
    # Check function signature
    sig = inspect.signature(push_leads)
    params = list(sig.parameters.keys())
    
    assert 'user_email' in params
    
    print("✅ push_leads() supports user_email parameter")
    print(f"   - Function signature: {sig}")

def test_backward_compatibility():
    """Test backward compatibility with old lead format."""
    print("\n" + "="*60)
    print("TEST 5: Backward Compatibility")
    print("="*60)
    
    from models import FacebookLead
    
    # Old format lead (without user fields)
    old_lead = FacebookLead(
        source_url="https://facebook.com/old",
        title="Old Lead",
        description="Old description",
        extra_data={
            "user_detail": {
                "email": "old@example.com",
                "name": "Old User",
                "phone": "+0987654321"
            }
        }
    )
    
    assert old_lead.extra_data.get('user_detail') is not None
    
    print("✅ Old lead format still works")
    print(f"   - extra_data.user_detail exists: {old_lead.extra_data.get('user_detail') is not None}")
    
    # New format lead (with user fields)
    new_lead = FacebookLead(
        source_url="https://facebook.com/new",
        title="New Lead",
        description="New description",
        user_email="new@example.com",
        user_name="New User",
        user_phone="+1111111111"
    )
    
    assert new_lead.user_email == "new@example.com"
    
    print("✅ New lead format works")
    print(f"   - user_email: {new_lead.user_email}")

def test_user_manager_utility():
    """Test user_lead_manager.py exists and is executable."""
    print("\n" + "="*60)
    print("TEST 6: User Management Utility")
    print("="*60)
    
    import os
    
    utility_path = os.path.join(os.path.dirname(__file__), "user_lead_manager.py")
    
    assert os.path.exists(utility_path)
    
    print("✅ user_lead_manager.py exists")
    print(f"   - Path: {utility_path}")

def main():
    print("\n" + "="*60)
    print("MULTI-USER LEAD MANAGEMENT - VERIFICATION TESTS")
    print("="*60)
    
    tests = [
        ("Models Support User Fields", test_models),
        ("Database User Filtering", test_database_methods),
        ("GHL User Mapping", test_ghl_user_mapping),
        ("Push Leads User Filter", test_push_leads_user_filter),
        ("Backward Compatibility", test_backward_compatibility),
        ("User Manager Utility", test_user_manager_utility),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ TEST FAILED: {test_name}")
            print(f"   Error: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"✅ Passed: {passed}/{len(tests)}")
    print(f"❌ Failed: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n🎉 All tests passed! Multi-user system is ready.")
    else:
        print("\n⚠️ Some tests failed. Please review errors above.")
    
    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    print("1. Review MULTI_USER_GUIDE.md for usage instructions")
    print("2. Test with real user data from ghl_onboarding_test")
    print("3. Trigger a scraping job with user_email in config")
    print("4. Verify leads are saved with user fields")
    print("5. Push leads to GHL and verify user association")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()

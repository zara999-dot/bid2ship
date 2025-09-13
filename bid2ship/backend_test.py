import requests
import sys
import json
from datetime import datetime, timedelta
import base64

class Bid2ShipAPITester:
    def __init__(self, base_url="https://bid2ship.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.shipper_auth = None
        self.driver_auth = None
        self.shipper_user = None
        self.driver_user = None
        self.test_shipment_id = None
        self.test_bid_id = None
        self.tests_run = 0
        self.tests_passed = 0

    def run_test(self, name, method, endpoint, expected_status, data=None, auth=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = f'Basic {auth}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return success, response.json()
                except:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Error: {error_detail}")
                except:
                    print(f"   Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test root API endpoint"""
        return self.run_test("Root API Endpoint", "GET", "", 200)

    def test_register_shipper(self):
        """Test shipper registration"""
        timestamp = datetime.now().strftime('%H%M%S')
        shipper_data = {
            "email": f"john{timestamp}@shipping.com",
            "password": "test123",
            "name": "John Smith",
            "phone": "+1-555-123-4567",
            "role": "shipper",
            "company_name": "ABC Logistics"
        }
        
        success, response = self.run_test(
            "Register Shipper",
            "POST",
            "users/register",
            200,
            data=shipper_data
        )
        
        if success:
            self.shipper_user = response
            # Create auth header for future requests
            auth_string = f"{shipper_data['email']}:{shipper_data['password']}"
            self.shipper_auth = base64.b64encode(auth_string.encode()).decode()
            print(f"   Shipper ID: {response.get('id')}")
        
        return success

    def test_register_driver(self):
        """Test driver registration"""
        timestamp = datetime.now().strftime('%H%M%S')
        driver_data = {
            "email": f"mike{timestamp}@driver.com",
            "password": "test123",
            "name": "Mike Johnson",
            "phone": "+1-555-987-6543",
            "role": "driver"
        }
        
        success, response = self.run_test(
            "Register Driver",
            "POST",
            "users/register",
            200,
            data=driver_data
        )
        
        if success:
            self.driver_user = response
            # Create auth header for future requests
            auth_string = f"{driver_data['email']}:{driver_data['password']}"
            self.driver_auth = base64.b64encode(auth_string.encode()).decode()
            print(f"   Driver ID: {response.get('id')}")
        
        return success

    def test_duplicate_registration(self):
        """Test duplicate email registration should fail"""
        if not self.shipper_user:
            print("❌ Skipping duplicate registration test - no shipper user")
            return False
            
        duplicate_data = {
            "email": self.shipper_user['email'],
            "password": "different123",
            "name": "Different Name",
            "phone": "+1-555-000-0000",
            "role": "shipper"
        }
        
        return self.run_test(
            "Duplicate Email Registration (should fail)",
            "POST",
            "users/register",
            400,
            data=duplicate_data
        )[0]

    def test_login_shipper(self):
        """Test shipper login"""
        if not self.shipper_user:
            print("❌ Skipping shipper login test - no shipper user")
            return False
            
        login_data = {
            "email": self.shipper_user['email'],
            "password": "test123"
        }
        
        return self.run_test(
            "Shipper Login",
            "POST",
            "users/login",
            200,
            data=login_data
        )[0]

    def test_get_current_user(self):
        """Test getting current user info"""
        if not self.shipper_auth:
            print("❌ Skipping current user test - no auth")
            return False
            
        return self.run_test(
            "Get Current User",
            "GET",
            "users/me",
            200,
            auth=self.shipper_auth
        )[0]

    def test_create_shipment(self):
        """Test creating a shipment (shipper only)"""
        if not self.shipper_auth:
            print("❌ Skipping shipment creation - no shipper auth")
            return False
            
        # Create deadline 7 days from now
        deadline = (datetime.now() + timedelta(days=7)).isoformat()
        
        shipment_data = {
            "origin_city": "New York, NY",
            "destination_city": "Los Angeles, CA",
            "description": "Electronics equipment - fragile handling required",
            "weight": 2.5,
            "deadline": deadline,
            "price_range": "$500 - $800"
        }
        
        success, response = self.run_test(
            "Create Shipment",
            "POST",
            "shipments",
            200,
            data=shipment_data,
            auth=self.shipper_auth
        )
        
        if success:
            self.test_shipment_id = response.get('id')
            print(f"   Shipment ID: {self.test_shipment_id}")
        
        return success

    def test_driver_cannot_create_shipment(self):
        """Test that drivers cannot create shipments"""
        if not self.driver_auth:
            print("❌ Skipping driver shipment test - no driver auth")
            return False
            
        deadline = (datetime.now() + timedelta(days=7)).isoformat()
        shipment_data = {
            "origin_city": "Chicago, IL",
            "destination_city": "Miami, FL",
            "description": "Test shipment",
            "weight": 1.0,
            "deadline": deadline
        }
        
        return self.run_test(
            "Driver Create Shipment (should fail)",
            "POST",
            "shipments",
            403,
            data=shipment_data,
            auth=self.driver_auth
        )[0]

    def test_get_shipments(self):
        """Test getting all shipments"""
        return self.run_test(
            "Get All Shipments",
            "GET",
            "shipments",
            200
        )[0]

    def test_get_posted_shipments(self):
        """Test getting only posted shipments"""
        return self.run_test(
            "Get Posted Shipments",
            "GET",
            "shipments?status=posted",
            200
        )[0]

    def test_get_my_shipments(self):
        """Test getting shipper's own shipments"""
        if not self.shipper_auth:
            print("❌ Skipping my shipments test - no shipper auth")
            return False
            
        return self.run_test(
            "Get My Shipments",
            "GET",
            "shipments/my",
            200,
            auth=self.shipper_auth
        )[0]

    def test_driver_cannot_get_my_shipments(self):
        """Test that drivers cannot access my shipments endpoint"""
        if not self.driver_auth:
            print("❌ Skipping driver my shipments test - no driver auth")
            return False
            
        return self.run_test(
            "Driver Get My Shipments (should fail)",
            "GET",
            "shipments/my",
            403,
            auth=self.driver_auth
        )[0]

    def test_get_shipment_by_id(self):
        """Test getting specific shipment by ID"""
        if not self.test_shipment_id:
            print("❌ Skipping get shipment by ID - no shipment ID")
            return False
            
        return self.run_test(
            "Get Shipment by ID",
            "GET",
            f"shipments/{self.test_shipment_id}",
            200
        )[0]

    def test_create_bid(self):
        """Test creating a bid (driver only)"""
        if not self.driver_auth or not self.test_shipment_id:
            print("❌ Skipping bid creation - missing driver auth or shipment ID")
            return False
            
        bid_data = {
            "shipment_id": self.test_shipment_id,
            "amount": 750.0,
            "message": "Experienced driver, can deliver on time with careful handling"
        }
        
        success, response = self.run_test(
            "Create Bid",
            "POST",
            "bids",
            200,
            data=bid_data,
            auth=self.driver_auth
        )
        
        if success:
            self.test_bid_id = response.get('id')
            print(f"   Bid ID: {self.test_bid_id}")
        
        return success

    def test_shipper_cannot_create_bid(self):
        """Test that shippers cannot create bids"""
        if not self.shipper_auth or not self.test_shipment_id:
            print("❌ Skipping shipper bid test - missing auth or shipment ID")
            return False
            
        bid_data = {
            "shipment_id": self.test_shipment_id,
            "amount": 600.0,
            "message": "Test bid"
        }
        
        return self.run_test(
            "Shipper Create Bid (should fail)",
            "POST",
            "bids",
            403,
            data=bid_data,
            auth=self.shipper_auth
        )[0]

    def test_duplicate_bid(self):
        """Test that drivers cannot bid twice on same shipment"""
        if not self.driver_auth or not self.test_shipment_id:
            print("❌ Skipping duplicate bid test - missing auth or shipment ID")
            return False
            
        bid_data = {
            "shipment_id": self.test_shipment_id,
            "amount": 700.0,
            "message": "Second bid attempt"
        }
        
        return self.run_test(
            "Duplicate Bid (should fail)",
            "POST",
            "bids",
            400,
            data=bid_data,
            auth=self.driver_auth
        )[0]

    def test_get_my_bids(self):
        """Test getting driver's own bids"""
        if not self.driver_auth:
            print("❌ Skipping my bids test - no driver auth")
            return False
            
        return self.run_test(
            "Get My Bids",
            "GET",
            "bids/my",
            200,
            auth=self.driver_auth
        )[0]

    def test_shipper_cannot_get_my_bids(self):
        """Test that shippers cannot access my bids endpoint"""
        if not self.shipper_auth:
            print("❌ Skipping shipper my bids test - no shipper auth")
            return False
            
        return self.run_test(
            "Shipper Get My Bids (should fail)",
            "GET",
            "bids/my",
            403,
            auth=self.shipper_auth
        )[0]

    def test_accept_bid(self):
        """Test accepting a bid (shipper only)"""
        if not self.shipper_auth or not self.test_bid_id:
            print("❌ Skipping accept bid test - missing auth or bid ID")
            return False
            
        return self.run_test(
            "Accept Bid",
            "PUT",
            f"bids/{self.test_bid_id}/accept",
            200,
            data={},
            auth=self.shipper_auth
        )[0]

    def test_driver_cannot_accept_bid(self):
        """Test that drivers cannot accept bids"""
        if not self.driver_auth or not self.test_bid_id:
            print("❌ Skipping driver accept bid test - missing auth or bid ID")
            return False
            
        return self.run_test(
            "Driver Accept Bid (should fail)",
            "PUT",
            f"bids/{self.test_bid_id}/accept",
            403,
            data={},
            auth=self.driver_auth
        )[0]

    def run_all_tests(self):
        """Run all API tests in sequence"""
        print("🚀 Starting Bid2Ship API Tests")
        print("=" * 50)
        
        # Basic API tests
        self.test_root_endpoint()
        
        # User registration and authentication
        self.test_register_shipper()
        self.test_register_driver()
        self.test_duplicate_registration()
        self.test_login_shipper()
        self.test_get_current_user()
        
        # Shipment management
        self.test_create_shipment()
        self.test_driver_cannot_create_shipment()
        self.test_get_shipments()
        self.test_get_posted_shipments()
        self.test_get_my_shipments()
        self.test_driver_cannot_get_my_shipments()
        self.test_get_shipment_by_id()
        
        # Bidding system
        self.test_create_bid()
        self.test_shipper_cannot_create_bid()
        self.test_duplicate_bid()
        self.test_get_my_bids()
        self.test_shipper_cannot_get_my_bids()
        self.test_accept_bid()
        self.test_driver_cannot_accept_bid()
        
        # Print results
        print("\n" + "=" * 50)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print(f"❌ {self.tests_run - self.tests_passed} tests failed")
            return 1

def main():
    tester = Bid2ShipAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
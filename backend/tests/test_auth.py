def test_local_profile_is_available_without_login(client):
    me = client.get("/api/users/me")
    assert me.status_code == 200
    assert me.json()["name"] == "Local Traveler"
    assert me.json()["email"] == "local@balatravel.app"

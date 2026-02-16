"""Test HTML page fixtures for browser controller tests."""

SIMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
    <h1>Example Domain</h1>
    <p>This is a test paragraph.</p>
    <button id="submit">Submit</button>
    <input id="search" type="text" placeholder="Search..." />
    <select id="country">
        <option value="us">United States</option>
        <option value="uk">United Kingdom</option>
    </select>
</body>
</html>
"""

FORM_HTML = """
<!DOCTYPE html>
<html>
<head><title>Form Test</title></head>
<body>
    <form id="login-form">
        <input id="username" type="text" />
        <input id="password" type="password" />
        <button type="submit" id="login-btn">Login</button>
    </form>
</body>
</html>
"""

DYNAMIC_HTML = """
<!DOCTYPE html>
<html>
<head><title>Dynamic Content</title></head>
<body>
    <div id="content">Loading...</div>
    <script>
        setTimeout(function() {
            document.getElementById('content').textContent = 'Loaded!';
        }, 100);
    </script>
</body>
</html>
"""

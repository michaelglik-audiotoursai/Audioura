import 'package:flutter/material.dart';
import '../services/subscription_service.dart';
import '../services/device_service.dart';
import '../screens/debug_log_viewer_screen.dart';

class SubscriptionCredentialDialog extends StatefulWidget {
  final String articleId;
  final String domain;
  final String articleTitle;
  final VoidCallback? onSuccess;

  const SubscriptionCredentialDialog({
    super.key,
    required this.articleId,
    required this.domain,
    required this.articleTitle,
    this.onSuccess,
  });

  @override
  State<SubscriptionCredentialDialog> createState() => _SubscriptionCredentialDialogState();
}

class _SubscriptionCredentialDialogState extends State<SubscriptionCredentialDialog> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isSubmitting = false;
  bool _obscurePassword = true;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(Icons.lock, color: Colors.orange, size: 24),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Subscription Required',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
          SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: Colors.orange.shade50,
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: Colors.orange.shade200),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Domain: ${widget.domain}',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: Colors.orange.shade800,
                  ),
                ),
                SizedBox(height: 4),
                Container(
                  width: double.infinity,
                  child: Text(
                    widget.articleTitle,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade700,
                    ),
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
      content: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.85,
          maxHeight: MediaQuery.of(context).size.height * 0.6,
        ),
        child: IntrinsicWidth(
          child: Column(
            mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _usernameController,
            decoration: InputDecoration(
              labelText: 'Username/Email',
              hintText: 'Enter your ${widget.domain} username',
              prefixIcon: Icon(Icons.person),
              border: OutlineInputBorder(),
            ),
            keyboardType: TextInputType.emailAddress,
            enabled: !_isSubmitting,
          ),
          SizedBox(height: 16),
          TextField(
            controller: _passwordController,
            decoration: InputDecoration(
              labelText: 'Password',
              hintText: 'Enter your ${widget.domain} password',
              prefixIcon: Icon(Icons.lock),
              suffixIcon: IconButton(
                icon: Icon(_obscurePassword ? Icons.visibility : Icons.visibility_off),
                onPressed: () {
                  setState(() {
                    _obscurePassword = !_obscurePassword;
                  });
                },
              ),
              border: OutlineInputBorder(),
            ),
            obscureText: _obscurePassword,
            enabled: !_isSubmitting,
          ),
          SizedBox(height: 16),
          Container(
            padding: EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.blue.shade50,
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: Colors.blue.shade200),
            ),
            child: Row(
              children: [
                Icon(Icons.security, color: Colors.blue.shade600, size: 16),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Your credentials are encrypted before transmission and stored securely.',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.blue.shade700,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _isSubmitting ? null : () => Navigator.pop(context),
          child: Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: _isSubmitting ? null : _submitCredentials,
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.orange,
            foregroundColor: Colors.white,
          ),
          child: _isSubmitting
              ? SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                )
              : Text('Submit'),
        ),
      ],
    );
  }

  Future<void> _submitCredentials() async {
    final username = _usernameController.text.trim();
    final password = _passwordController.text.trim();

    // DEBUG: Log actual input values
    await DebugLogHelper.addDebugLog('CREDENTIAL_DEBUG: Username input: "$username" (length: ${username.length})');
    await DebugLogHelper.addDebugLog('CREDENTIAL_DEBUG: Password input: "$password" (length: ${password.length})');
    await DebugLogHelper.addDebugLog('CREDENTIAL_DEBUG: Username isEmpty: ${username.isEmpty}');
    await DebugLogHelper.addDebugLog('CREDENTIAL_DEBUG: Password isEmpty: ${password.isEmpty}');

    if (username.isEmpty || password.isEmpty) {
      await DebugLogHelper.addDebugLog('CREDENTIAL_DEBUG: ERROR - Empty credentials detected');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Please enter both username and password'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    setState(() {
      _isSubmitting = true;
    });

    try {
      await DebugLogHelper.addDebugLog('SUBSCRIPTION_DIALOG: Submitting credentials for article: ${widget.articleId}');
      await DebugLogHelper.addDebugLog('CREDENTIAL_DEBUG: About to encrypt - Username: "$username", Password: "$password"');
      
      final deviceId = await DeviceService.getUserId();
      
      final success = await SubscriptionService.submitCredentials(
        articleId: widget.articleId,
        username: username,
        password: password,
        deviceId: deviceId,
        domain: widget.domain,
      );

      if (mounted) {
        Navigator.pop(context);
        await Future.delayed(Duration(milliseconds: 100));
        
        if (success) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Successfully entered credentials for ${widget.domain}'),
              backgroundColor: Colors.green,
              action: SnackBarAction(
                label: 'OK',
                textColor: Colors.white,
                onPressed: () {},
              ),
            ),
          );
          widget.onSuccess?.call();
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failure to send credentials for processing: Encryption keys not available. Please try again later.'),
              backgroundColor: Colors.red,
              action: SnackBarAction(
                label: 'Retry',
                textColor: Colors.white,
                onPressed: () => _showCredentialDialog(),
              ),
            ),
          );
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUBSCRIPTION_DIALOG: Error submitting credentials: $e');
      
      if (mounted) {
        Navigator.pop(context);
        await Future.delayed(Duration(milliseconds: 100));
        
        String userMessage = 'Failure to send credentials for processing: ';
        if (e.toString().contains('No mobile public key available')) {
          userMessage += 'Encryption keys not available. Please try again later.';
        } else {
          userMessage += 'Network or server error. Please check your connection.';
        }
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(userMessage),
            backgroundColor: Colors.red,
            action: SnackBarAction(
              label: 'Retry',
              textColor: Colors.white,
              onPressed: () => _showCredentialDialog(),
            ),
          ),
        );
      }
    }
  }

  void _showCredentialDialog() {
    showDialog(
      context: context,
      builder: (context) => SubscriptionCredentialDialog(
        articleId: widget.articleId,
        domain: widget.domain,
        articleTitle: widget.articleTitle,
        onSuccess: widget.onSuccess,
      ),
    );
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }
}
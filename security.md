# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | :white_check_mark: |
| 1.x.x   | :x:                |

## Security Measures

### Authentication & Authorization

- Admin commands protected by user ID whitelist
- Scripts require API key authentication
- No auto-subscribe - explicit admin approval required
- Audit logging for all administrative actions

### Data Protection

- No secrets in code or logs
- Environment-based configuration
- Parameterized SQL queries (ORM)
- Input validation for all user inputs

### Container Security

- Non-root user in Docker
- Read-only filesystem where possible
- No unnecessary capabilities
- Private network isolation

### Network Security

- Timeouts on all network operations
- Rate limiting on message sending
- No SSH or remote code execution
- TLS for all external connections

## Reporting a Vulnerability

**DO NOT** open a public issue for security vulnerabilities.

Email: turtle_bp@proton.me

Include:
- Description of vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond as soon as possible

## Best Practices for Operators

1. **Use strong API keys**: Generate random 32+ character keys
2. **Restrict admin access**: Only add trusted user IDs to ADMIN_USER_IDS
3. **Regular updates**: Keep dependencies updated
4. **Monitor logs**: Check for suspicious activity
5. **Use PostgreSQL in production**: Better security than SQLite for multi-user
6. **Enable HTTPS**: If exposing any HTTP endpoints
7. **Backup regularly**: Automated backups with encryption
8. **Least privilege**: Run bot with minimal system permissions

## Known Limitations

- SQLite file-based DB: Ensure proper file permissions (600)
- No built-in authentication for metrics endpoint (if added)
- Rate limiting is per-chat, not global

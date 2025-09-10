---
category: "user_facing"
context: "verification_flow"
variables:
  - name: "user_handle"
    type: "string"
    description: "RSI handle being verified"
  - name: "organization_name"
    type: "string"
    description: "Target organization name (TEST Squadron)"
  - name: "member_mention"
    type: "string"
    description: "Discord mention of the member"
  - name: "status"
    type: "string"
    enum: ["main", "affiliate"]
    description: "Membership status determined"
schemas:
  - "discord_events.json#/member"
  - "api_responses.json#/verification_result"
ai_hints:
  - "This template announces successful verification to the community"
  - "Status determines role assignment and access level"
  - "Organization name should match exactly from RSI data"
---

# Verification Success Messages

## Successful Verification Announcement

**Template ID**: `verification_success`
**Usage**: Posted to announcement channel when verification completes

🗂️ {member_mention} verified as {status} member

**Variables**:
- `member_mention`: Discord mention string (e.g., `<@123456789>`)
- `status`: Either "main" or "affiliate" 

**Example Output**:
```
🗂️ <@123456789> verified as main member
```

---

## Verification Token Request

**Template ID**: `verification_token_request`
**Usage**: DM sent to user requesting verification token

### Template
```
🔐 **Verification Token Required**

To complete your verification for **{organization_name}**, please:

1. Visit: https://robertsspaceindustries.com/account/settings
2. Set your bio to include this token: `{verification_token}`
3. Return here and try verification again

⏰ This token expires in 10 minutes.
🔒 Your bio will be checked automatically.

**Need help?** Contact a staff member.
```

**Variables**:
- `organization_name`: Organization being verified for
- `verification_token`: Unique verification token

---

## Verification Rate Limited

**Template ID**: `verification_rate_limited`
**Usage**: Response when user hits rate limit

### Template
```
⏱️ **Rate Limited**

Please wait {retry_after} seconds before trying verification again.

This helps prevent spam and ensures fair access for everyone.
```

**Variables**:
- `retry_after`: Number of seconds to wait

---

## Verification Failed - Not Found

**Template ID**: `verification_failed_not_found`
**Usage**: When RSI handle is not found or inaccessible

### Template
```
❌ **Verification Failed**

Could not find RSI handle: `{user_handle}`

**Common issues**:
- Handle doesn't exist
- Profile is private
- Temporary RSI website issues

**Solutions**:
- Check your handle spelling
- Make sure your RSI profile is public
- Try again in a few minutes
```

**Variables**:
- `user_handle`: The RSI handle that failed verification

---

## Verification Failed - Not Member

**Template ID**: `verification_failed_not_member`
**Usage**: When handle exists but user is not in required organization

### Template
```
❌ **Verification Failed**

RSI handle `{user_handle}` found, but you are not a member of **{organization_name}**.

**To join**:
1. Visit the organization page on RSI website
2. Submit an application
3. Wait for approval
4. Return here to verify

**Already a member?** Check that your organization membership is set to public.
```

**Variables**:
- `user_handle`: The RSI handle
- `organization_name`: Required organization name

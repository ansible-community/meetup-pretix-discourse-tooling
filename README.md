WIP: Ansible Community Tooling for migration from Meetup Pro to Discourse + pretix
=======
 Prototype for:
 * Discourse: Source of Truth
 * prefix: RSVP
 * Luma: Discoverability


# Discourse Connect MVP

Get the `localhost` secret from [forum settings](https://forum.ansible.com/admin/site_settings/category/all_results?filter=connect%20provider).
```
export DISCOURSE_API_USERNAME=gundalow
export DISCOURSE_API_KEY=REDACTED
export DISCOURSE_SSO_SECRET=REDACTED
uv run scripts/discourse-connect-mvp.py
```

Browser: http://localhost:5000

Errors: https://forum.ansible.com/logs/

# Pretix plugin

`~/.pretix.cfg`
```[pretix]
# Append to any existing backends (comma separated)
auth_backends=pretix.base.auth.NativeAuthBackend,pretix_discourse_auth.backend.DiscourseAuthBackend
```

## Install Pretix Auth plugin

```
git clone git@github.com:ansible-community/meetup-pretix-discourse-auth.git
cd pretix-discourse-auth
pip install -e .
```


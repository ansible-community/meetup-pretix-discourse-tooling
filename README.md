WIP: Ansible Community Tooling for migration from Meetup Pro to Discourse + pretix
=======
 Prototype for:
 * Discourse: Source of Truth
 * prefix: RSVP
 * Luma: Discoverability


The production sign-in flow is provided by the separate `meetup-pretix-discourse-auth` plugin. This repository contains provisioning and event-management tooling; it does not include a local SSO prototype.

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

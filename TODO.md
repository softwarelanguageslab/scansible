# Known limitations

- The SCA needs to resolve collections to identify dependencies.
  It currently resolves against the collections that are included in the `ansible`
  release that is packaged with SCAnsible, which may be outdated or not match
  the collection versions that are used in practice. This may lead to incorrect
  output.
  FIX: Instead of using the packaged collections, resolve collections against
  the Ansible installation that is used to run the playbooks that are analysed.
  Afterwards, it'll also be possible to remove the dependency on `ansible` and
  depend solely on `ansible-core`, which doesn't include the collections.

- SCAnsible heavily relies on Ansible to parse and validate code, as well as for
  several other utilities. This is a rather heavy dependency, and importing Ansible
  slows down SCAnsible's initial start. Moreover, the parsing logic is full of hacks
  to work around issues arising from the reliance on Ansible.
  FIX: We should reduce and ideally remove the dependency on Ansible. For starters,
  parsing and validating can be reimplemented to avoid the hacks.

- SCAnsible writes many cache files to the `cache` directory in the current working
  directory. These are not project-specific, are not refreshed, and should likely be
  stored elsewhere.

  - `ecosystems_cache.json` and `debian_advisories.json` contain advisory information
    for the detected dependencies. These should be refreshed periodically.
  - `collection_content.json` stores names and parameters of all modules in the
    scanned collections. This is not yet extracted automatically, and should be project-specific.
  - `dep_cache.json` and `smells_cache.json` caches results of dependency detection
    and smell detection, respectively. These should be project-specific and invalidated
    when the code changes.

- SCAnsible security advisories for OS binaries relies on Debian Security advisories.
  This may not be appropriate for packages on other Linux distros.
  FIX: Need to map OS binaries to correct distros and use the appropriate
  advisory database.

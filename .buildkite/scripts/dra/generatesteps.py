import os
import sys

import yaml

def to_bk_key_friendly_string(key):
    """
    Convert and return key to an acceptable format for Buildkite's key: field
    Only alphanumerics, dashes and underscores are allowed.
    """

    mapping_table = str.maketrans({'.': '_'})

    return key.translate(mapping_table)

def package_x86_step(branch, workflow_type):
    step = f'''
- label: ":package: Build packages / {branch}-{workflow_type.upper()} DRA artifacts"
  key: "logstash_build_packages_dra"
  agents:
    image: "docker.elastic.co/ci-agent-images/platform-ingest/buildkite-agent-logstash-ci:0.2"
    cpu: "8"
    memory: "16Gi"
    ephemeralStorage: "200Gi"
  command: |
    export WORKFLOW_TYPE="{workflow_type}"
    export PATH="/usr/local/rbenv/bin:$PATH"
    eval "$(rbenv init -)"
    .buildkite/scripts/dra/build_packages.sh
'''

    return step

def package_x86_docker_step(branch, workflow_type):
    step = f'''
- label: ":package: Build x86_64 Docker / {branch}-{workflow_type.upper()} DRA artifacts"
  key: "logstash_build_x86_64_docker_dra"
  agents:
    provider: gcp
    imageProject: elastic-images-qa
    image: family/platform-ingest-logstash-ubuntu-2204
    machineType: "n2-standard-16"
    diskSizeGb: 200
  command: |
    export WORKFLOW_TYPE="{workflow_type}"
    export PATH="/opt/buildkite-agent/.rbenv/bin:/opt/buildkite-agent/.pyenv/bin:$PATH"
    export ARCH="x86_64"
    eval "$(rbenv init -)"
    .buildkite/scripts/dra/build_docker.sh
'''

    return step

def package_aarch64_docker_step(branch, workflow_type):
    step = f'''
- label: ":package: Build aarch64 Docker / {branch}-{workflow_type.upper()} DRA artifacts"
  key: "logstash_build_aarch64_docker_dra"
  agents:
    provider: gcp
    imageProject: elastic-images-qa
    image: family/platform-ingest-logstash-ubuntu-2204-aarch64
    machineType: "t2a-standard-8"
    diskSizeGb: 200
    region: 'us-central1'
    # so far only these regions support t2a instance types
    zones: "us-central1-a,us-central1-b,us-central1-f"
  command: |
    export WORKFLOW_TYPE="{workflow_type}"
    export PATH="/opt/buildkite-agent/.rbenv/bin:/opt/buildkite-agent/.pyenv/bin:$PATH"
    export ARCH="aarch64"
    eval "$(rbenv init -)"
    .buildkite/scripts/dra/build_docker.sh
'''

    return step

def publish_dra_step(branch, workflow_type, depends_on):
    step = f'''
- label: ":elastic-stack: Publish  / {branch}-{workflow_type.upper()} DRA artifacts"
  key: "logstash_publish_dra"
  depends_on: "{depends_on}"
  agents:
    provider: gcp
    imageProject: elastic-images-qa
    image: family/platform-ingest-logstash-ubuntu-2204
    machineType: "n2-standard-16"
    diskSizeGb: 200
  command: |
    echo "+++ Restoring Artifacts"
    buildkite-agent artifact download "build/logstash*" .
    buildkite-agent artifact download "build/distributions/**/*" .
    echo "+++ Changing permissions for the release manager"
    sudo chown -R :1000 build
    echo "+++ Running DRA publish step"
    export WORKFLOW_TYPE="{workflow_type}"
    .buildkite/scripts/dra/publish.sh
    '''

    return step

def build_steps_to_yaml(branch, workflow_type):
    steps = []
    steps.extend(yaml.safe_load(package_x86_step(branch, workflow_type)))
    steps.extend(yaml.safe_load(package_x86_docker_step(branch, workflow_type)))
    steps.extend(yaml.safe_load(package_aarch64_docker_step(branch, workflow_type)))

    return steps

if __name__ == "__main__":
    try:
        workflow_type = os.environ["WORKFLOW_TYPE"]
    except ImportError:
        print(f"Missing env variable WORKFLOW_TYPE. Use export WORKFLOW_TYPE=<staging|snapshot>\n.Exiting.")
        exit(1)

    branch = os.environ["BUILDKITE_BRANCH"]

    structure = {"steps": []}

    # Group defining parallel steps that build and save artifacts
    group_key = to_bk_key_friendly_string(f"logstash_dra_{workflow_type}")

    structure["steps"].append({
        "group": f":Build Artifacts - {workflow_type.upper()}",
        "key": group_key,
        "steps": build_steps_to_yaml(branch, workflow_type),
    })

    # Final step: pull artifacts built above and publish them via the release-manager
    structure["steps"].extend(
        yaml.safe_load(publish_dra_step(branch, workflow_type, depends_on=group_key)),
    )

    print(yaml.dump(structure, Dumper=yaml.Dumper, sort_keys=False))
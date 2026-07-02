# k8s-psql: run psql inside an ephemeral pod in the current kube context.
#
# Env:
#   PGPASSWORD           forwarded to the pod if set
#   K8S_PSQL_NAMESPACE   pod namespace (default: default)
#   K8S_PSQL_IMAGE       image with psql (default: postgres:16-alpine)
#
# Args: passed verbatim to psql inside the pod.
# Examples:
#   k8s-psql -h my-db.internal -U river -d arcade_engine
#   PGPASSWORD=hunter2 k8s-psql -h my-db.internal -U river -d arcade_engine
#   k8s-psql "postgresql://river@my-db.internal:5432/arcade_engine"
k8s-psql() {
  (
    set -eu
    local ns="${K8S_PSQL_NAMESPACE:-default}"
    local image="${K8S_PSQL_IMAGE:-postgres:16-alpine}"
    local ctx
    ctx="$(kubectl config current-context)"
    local pod="psql-shell-${USER}-$$-${RANDOM}"

    local env_args=()
    [ -n "${PGPASSWORD:-}" ] && env_args=(--env "PGPASSWORD=${PGPASSWORD}")

    echo "k8s-psql: context=${ctx} namespace=${ns} pod=${pod}" >&2

    # Belt-and-suspenders cleanup — --rm handles graceful exit, but if the
    # exec stream dies before --rm engages, the trap still deletes the pod.
    trap 'kubectl --context "'"$ctx"'" -n "'"$ns"'" delete pod "'"$pod"'" --wait=false --ignore-not-found >/dev/null 2>&1 || true' EXIT

    kubectl --context "$ctx" -n "$ns" run "$pod" \
      --rm -i --tty --restart=Never \
      --image="$image" \
      "${env_args[@]}" \
      --command -- psql "$@"
  )
}

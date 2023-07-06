# Alberto Gonzalez <albert.gonzalez@redhat.com> 2023

from kubernetes import client, config, watch
import json, os, time

kubernetes_host = os.getenv("KUBERNETES_SERVICE_HOST")
kubernetes_port = os.getenv("KUBERNETES_SERVICE_PORT")

internal_endpoint = f"https://{kubernetes_host}:{kubernetes_port}"
token = open("/run/secrets/kubernetes.io/serviceaccount/token").read()
namespace = open("/run/secrets/kubernetes.io/serviceaccount/namespace").read()
ca_cert = "/run/secrets/kubernetes.io/serviceaccount/ca.crt"


# Create a Kubernetes configuration object
configuration = client.Configuration()
configuration.host = internal_endpoint
configuration.api_key['authorization'] = token
configuration.api_key_prefix['authorization'] = 'Bearer'
configuration.ssl_ca_cert = ca_cert


configuration.verify_ssl = True # Set to False if you want to skip SSL verification

kube_client = client.ApiClient(configuration)

# List the virtual machines
api = client.CustomObjectsApi(kube_client)
w = watch.Watch()
for event in w.stream(api.list_namespaced_custom_object, group="kubevirt.io", version="v1", plural="virtualmachines", namespace=namespace):
    if event['type'] == 'MODIFIED':
        vm = event['object']
        name = vm['metadata']['name']
        if vm['spec']['running'] == True and 'trackvm' not in vm['metadata']['annotations']:
            vmi = api.get_namespaced_custom_object(group="kubevirt.io", version="v1", plural="virtualmachineinstances", namespace=namespace, name=name)
            vm_domain = vm['spec']['template']['spec']['domain'] 
            vmi_domain = vmi['spec']['domain']
            if (vm_domain['cpu']['cores'] != vmi_domain['cpu']['cores']) or  (vm_domain['resources']['requests']['memory'] != vmi_domain['resources']['requests']['memory']):
                patch = [
                    {"op": "add", "path": "/metadata/annotations/trackvm", "value": "stop_triggered"},
                    {"op": "replace", "path": "/spec/running", "value": False}
                ]
                # Patch the object
                api.api_client.set_default_header('Content-Type', 'application/json-patch+json')
                print("Stopping vm " + name)
                api.patch_namespaced_custom_object(
                    group="kubevirt.io",
                    version="v1",
                    plural="virtualmachines",
                    name=name,
                    namespace=namespace,
                    body=patch,
                )
                # Wait till the VMI doesnt exist
                vmi_exists = True
                while vmi_exists:
                    time.sleep(1)
                    try:
                        vmi = api.get_namespaced_custom_object(group="kubevirt.io", version="v1", plural="virtualmachineinstances", namespace=namespace, name=name)
                    except:
                        vmi_exists = False

        if vm['spec']['running'] == False and 'trackvm' in vm['metadata']['annotations'] and vm['metadata']['annotations']['trackvm'] == "stop_triggered":
            patch = [
                {"op": "replace", "path": "/spec/running", "value": True},
                {"op": "remove", "path": "/metadata/annotations/trackvm"}
            ]
            api.api_client.set_default_header('Content-Type', 'application/json-patch+json')
            print("Starting vm " + name)
            api.patch_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                plural="virtualmachines",
                name=name,
                namespace=namespace,
                body=patch,
            )

            while not vmi_exists:
                time.sleep(1)
                try:
                    vmi = api.get_namespaced_custom_object(group="kubevirt.io", version="v1", plural="virtualmachineinstances", namespace=namespace, name=name)
                except:
                    vmi_exists = True



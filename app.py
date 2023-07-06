# Alberto Gonzalez <albert.gonzalez@redhat.com> 2023

from kubernetes import client, config, watch
import json, os

kubernetes_host = os.getenv("KUBERNETES_SERVICE_HOST")
kubernetes_port = os.getenv("KUBERNETES_SERVICE_PORT")

internal_endpoint = f"https://{kubernetes_host}:{kubernetes_port}"
token = open("/run/secrets/kubernetes.io/serviceaccount/token").read()
namespace = open("/run/secrets/kubernetes.io/serviceaccount/namespace").read()


# Create a Kubernetes configuration object
configuration = client.Configuration()
configuration.host = internal_endpoint
configuration.api_key['authorization'] = token
configuration.api_key_prefix['authorization'] = 'Bearer'

configuration.verify_ssl = False # Set to False if you want to skip SSL verification

kube_client = client.ApiClient(configuration)

# List the virtual machines
api = client.CustomObjectsApi(kube_client)
w = watch.Watch()
for event in w.stream(api.list_namespaced_custom_object, group="kubevirt.io", version="v1", plural="virtualmachines", namespace=namespace):
    if event['type'] == 'MODIFIED':
        vm = event['object']
        name = vm['metadata']['name']
        if vm['spec']['running'] == True:
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
        if vm['spec']['running'] == False and 'trackvm' in vm['metadata']['annotations'] and vm['metadata']['annotations']['trackvm'] == "stop_triggered":
            patch = [
                {"op": "replace", "path": "/spec/running", "value": True},
                {"op": "remove", "path": "/metadata/annotations/trackvm"}
            ]
            api.api_client.set_default_header('Content-Type', 'application/json-patch+json')
            print("Start vm " + name)
            try:
                api.patch_namespaced_custom_object(
                    group="kubevirt.io",
                    version="v1",
                    plural="virtualmachines",
                    name=name,
                    namespace=namespace,
                    body=patch,
                )
            except:
                print("Error starting the VM " + name)
     

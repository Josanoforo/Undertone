# External viewer gateway boundary

The supplied gateway is a loopback proxy, not hosting or TLS termination. A separately provisioned trusted HTTPS ingress must preserve the expected Host/Origin, strip spoofable forwarding/marker headers and route only to the gateway. Keep the backend private. Configure the backend and gateway with the same process-only random gateway secret and exact public HTTPS origin.

`scripts/Start-Gateway.ps1` performs configuration/bind preflight; its explicit Execute mode starts the gateway. Preflight does not establish ingress availability, valid remote-device access or compatibility acceptance. No secret or usable operator invitation is distributed. The evaluator must provision its own deployment and access configuration.

"use client";

import { X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  ConnectivityTestBody,
  ProviderCreateBody,
} from "@/lib/api/server/providers";
import type { ConnectivityTestOut } from "@/lib/api/shared/types";

import {
  AddProviderActions,
  ConnectivityResultAlert,
  ProviderConnectionFields,
  ProviderFormOptions,
  ProviderTypePicker,
  type ConnectivityResult,
  type ProviderKind,
} from "./add-provider-form-fields";

/** New-provider form card — type/URL/key + connectivity probe before save. */
export function AddProviderForm({
  onClose,
  onTestConnection,
  onCreate,
  onCreated,
}: {
  onClose: () => void;
  onTestConnection: (body: ConnectivityTestBody) => Promise<ConnectivityTestOut>;
  onCreate: (body: ProviderCreateBody) => Promise<unknown>;
  onCreated: () => void;
}) {
  const [type, setType] = useState<ProviderKind>("ollama");
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("http://localhost:11434");
  const [apiKey, setApiKey] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [skipTest, setSkipTest] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ConnectivityResult | null>(null);

  const onTypeChange = (next: ProviderKind) => {
    setType(next);
    setTestResult(null);
    if (next === "ollama" && (!baseUrl || baseUrl.includes("openai"))) {
      setBaseUrl("http://localhost:11434");
    }
    if (next === "openai" && baseUrl.includes("11434")) {
      setBaseUrl("https://api.openai.com/v1");
    }
  };

  const onTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      setTestResult(
        await onTestConnection({
          type,
          base_url: baseUrl,
          api_key: apiKey || undefined,
        })
      );
    } catch (err) {
      setTestResult({ ok: false, detail: (err as Error).message });
    } finally {
      setTesting(false);
    }
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onCreate({
        name: name.trim(),
        type,
        base_url: baseUrl,
        api_key: apiKey || undefined,
        is_default: isDefault,
        test_connectivity: !skipTest,
      });
      onCreated();
    } catch (err) {
      setTestResult({ ok: false, detail: (err as Error).message });
    } finally {
      setSubmitting(false);
    }
  };

  const clearTestResult = () => setTestResult(null);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Add a provider</CardTitle>
          <CardDescription>
            Type, URL, and (if needed) an API key. We probe the endpoint before saving
            unless you opt out.
          </CardDescription>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Cancel">
          <X />
        </Button>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={onSubmit}>
          <ProviderTypePicker value={type} onChange={onTypeChange} />
          <ProviderConnectionFields
            type={type}
            name={name}
            baseUrl={baseUrl}
            apiKey={apiKey}
            onNameChange={setName}
            onBaseUrlChange={(next) => {
              setBaseUrl(next);
              clearTestResult();
            }}
            onApiKeyChange={(next) => {
              setApiKey(next);
              clearTestResult();
            }}
          />
          <ProviderFormOptions
            isDefault={isDefault}
            skipTest={skipTest}
            onDefaultChange={setIsDefault}
            onSkipTestChange={setSkipTest}
          />
          <ConnectivityResultAlert result={testResult} />
          <AddProviderActions
            testing={testing}
            submitting={submitting}
            canTest={Boolean(baseUrl)}
            canSubmit={Boolean(name.trim())}
            onTest={onTest}
          />
        </form>
      </CardContent>
    </Card>
  );
}

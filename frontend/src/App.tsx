import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { HomePage } from "./pages/HomePage";
import { WorkspacePage } from "./pages/WorkspacePage";
import { KnowledgePage } from "./pages/KnowledgePage";

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/workspace/:id" element={<WorkspacePage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

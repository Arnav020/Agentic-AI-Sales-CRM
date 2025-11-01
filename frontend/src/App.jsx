import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Home from "./components/Home";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Inputs from "./pages/Inputs"; 
import Agents from "./pages/Agents";

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/auth" element={<Auth />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/inputs" element={<Inputs />} />
        <Route path="/agents" element={<Agents />} />
      </Routes>
    </Router>
  );
}

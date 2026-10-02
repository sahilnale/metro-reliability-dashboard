import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./leafletIcons";
import HomePage from "./pages/HomePage";
import RoutePage from "./pages/RoutePage";
import StopPage from "./pages/StopPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/routes/:routeId" element={<RoutePage />} />
        <Route path="/stops/:stopId" element={<StopPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;

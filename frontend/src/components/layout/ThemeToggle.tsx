import { Moon, Sun } from "lucide-react";
import { Button } from "../ui/button";
import { useTheme } from "../theme-provider";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const nextTheme = theme === "light" ? "dark" : "light";

  return (
    <Button
      aria-label={`Switch to ${nextTheme} mode`}
      className="text-foreground"
      onClick={toggleTheme}
      size="icon"
      variant="secondary"
    >
      {theme === "light" ? (
        <Moon aria-hidden="true" size={18} />
      ) : (
        <Sun aria-hidden="true" size={18} />
      )}
    </Button>
  );
}

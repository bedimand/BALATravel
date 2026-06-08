import Image from "next/image";

import icon from "@/img/icone.png";

type Props = {
  /** Pixel size of the square icon. */
  size?: number;
  /** Show the "BALATravel" wordmark next to the icon. */
  withWordmark?: boolean;
  className?: string;
};

// Single source of truth for the BALATravel mark across the app. The icon file
// lives in /img and is also surfaced as the favicon/apple-icon via app/icon.png.
export function BrandLogo({ size = 40, withWordmark = false, className }: Props) {
  return (
    <span className={`brand-logo${className ? ` ${className}` : ""}`}>
      <Image
        src={icon}
        alt="BALATravel"
        width={size}
        height={size}
        priority
        className="brand-logo__icon"
      />
      {withWordmark ? (
        <span className="brand-logo__wordmark">
          BALA<span>Travel</span>
        </span>
      ) : null}
    </span>
  );
}

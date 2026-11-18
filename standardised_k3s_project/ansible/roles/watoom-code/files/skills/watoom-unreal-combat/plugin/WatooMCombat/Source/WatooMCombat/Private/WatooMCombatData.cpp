#include "WatooMCombatData.h"

float UWatooMWeaponData::FalloffMultiplier(float Distance) const
{
	if (Distance <= FalloffStart || FalloffEnd <= FalloffStart) { return Distance <= FalloffStart ? 1.f : FalloffMinMultiplier; }
	if (Distance >= FalloffEnd) { return FalloffMinMultiplier; }
	const float T = (Distance - FalloffStart) / (FalloffEnd - FalloffStart);
	return FMath::Lerp(1.f, FalloffMinMultiplier, T);
}

#pragma once

#include "NativeGameplayTags.h"

// Native tags every WatooMCombat game shares. Data assets may add their own (Ability.Spell.Fireball, Damage.Type.Poison, ...)
// through the project's tag config; these are the ones the C++ reads.
namespace WatooMTags
{
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(SetByCaller_Damage);          // Data.Damage: base damage of one hit
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(SetByCaller_DamageMultiplier); // Data.DamageMultiplier: headshot/zone/falloff
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(SetByCaller_Healing);         // Data.Healing
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(SetByCaller_Stamina);         // Data.Cost.Stamina (positive = cost)
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(SetByCaller_Mana);            // Data.Cost.Mana (positive = cost)
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(SetByCaller_Ammo);            // Data.Cost.Ammo (positive = rounds used)
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(SetByCaller_Duration);        // Data.Duration: cooldown / status length
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Damage_Type_Physical);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Damage_Type_Fire);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Damage_Type_Frost);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Damage_Type_Lightning);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Dead);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Stunned);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Reloading);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Event_Death);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Event_Hit);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Event_MeleeWindowOpen);   // anim notify -> ability: start blade traces
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Event_MeleeWindowClose);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Event_Fire);              // anim notify -> ability: spawn shot/projectile now
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Melee);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Gun);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Spell);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Reload);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Cooldown);                // parent of every Cooldown.<Ability> tag
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Cooldown_Melee);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(Cooldown_Gun);
	WATOOMCOMBAT_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayCue_Hit);          // GameplayCue.Combat.Hit
}

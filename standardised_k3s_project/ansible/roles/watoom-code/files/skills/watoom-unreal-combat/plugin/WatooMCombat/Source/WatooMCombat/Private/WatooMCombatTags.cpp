#include "WatooMCombatTags.h"

namespace WatooMTags
{
	UE_DEFINE_GAMEPLAY_TAG_COMMENT(SetByCaller_Damage, "Data.Damage", "Base damage of one hit (SetByCaller)");
	UE_DEFINE_GAMEPLAY_TAG_COMMENT(SetByCaller_DamageMultiplier, "Data.DamageMultiplier", "Headshot / zone / falloff multiplier (SetByCaller)");
	UE_DEFINE_GAMEPLAY_TAG_COMMENT(SetByCaller_Healing, "Data.Healing", "Healing amount (SetByCaller)");
	UE_DEFINE_GAMEPLAY_TAG_COMMENT(SetByCaller_Stamina, "Data.Cost.Stamina", "Stamina cost (SetByCaller, positive)");
	UE_DEFINE_GAMEPLAY_TAG_COMMENT(SetByCaller_Mana, "Data.Cost.Mana", "Mana cost (SetByCaller, positive)");
	UE_DEFINE_GAMEPLAY_TAG_COMMENT(SetByCaller_Ammo, "Data.Cost.Ammo", "Rounds used (SetByCaller, positive)");
	UE_DEFINE_GAMEPLAY_TAG_COMMENT(SetByCaller_Duration, "Data.Duration", "Cooldown or status duration in seconds (SetByCaller)");
	UE_DEFINE_GAMEPLAY_TAG(Damage_Type_Physical, "Damage.Type.Physical");
	UE_DEFINE_GAMEPLAY_TAG(Damage_Type_Fire, "Damage.Type.Fire");
	UE_DEFINE_GAMEPLAY_TAG(Damage_Type_Frost, "Damage.Type.Frost");
	UE_DEFINE_GAMEPLAY_TAG(Damage_Type_Lightning, "Damage.Type.Lightning");
	UE_DEFINE_GAMEPLAY_TAG(State_Dead, "State.Dead");
	UE_DEFINE_GAMEPLAY_TAG(State_Stunned, "State.Stunned");
	UE_DEFINE_GAMEPLAY_TAG(State_Reloading, "State.Reloading");
	UE_DEFINE_GAMEPLAY_TAG(Event_Death, "Event.Death");
	UE_DEFINE_GAMEPLAY_TAG(Event_Hit, "Event.Hit");
	UE_DEFINE_GAMEPLAY_TAG(Event_MeleeWindowOpen, "Event.Melee.WindowOpen");
	UE_DEFINE_GAMEPLAY_TAG(Event_MeleeWindowClose, "Event.Melee.WindowClose");
	UE_DEFINE_GAMEPLAY_TAG(Event_Fire, "Event.Fire");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Melee, "Ability.Melee");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Gun, "Ability.Gun");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Spell, "Ability.Spell");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Reload, "Ability.Reload");
	UE_DEFINE_GAMEPLAY_TAG(Cooldown, "Cooldown");
	UE_DEFINE_GAMEPLAY_TAG(Cooldown_Melee, "Cooldown.Melee");
	UE_DEFINE_GAMEPLAY_TAG(Cooldown_Gun, "Cooldown.Gun");
	UE_DEFINE_GAMEPLAY_TAG(GameplayCue_Hit, "GameplayCue.Combat.Hit");
}
